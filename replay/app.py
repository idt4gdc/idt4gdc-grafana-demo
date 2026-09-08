"""
Replays a stored ExaDigiT simulation export (see idt4gdc-digital-twins'
loadtest/export_sim.py) into telemetry_metrics as if it were live telemetry.

Seeds a dedicated room/rack/asset topology (asset ids prefixed "dt-") derived
from whichever nodes actually appear in the export, so this never touches the
existing synthetic srv-01..24 demo assets -- it just adds a new selectable
room in the existing room/rack/server dashboard filters.

Real per-job power from the export is split evenly across a job's assigned
nodes (ExaDigiT reports job-total power, not per-node).
Nodes with no job running at a given moment fall back to an idle-power baseline.
cpu_usage/carbon are derived from that real power using the same shapes
simulator.py uses for the synthetic assets, so panels/alerts built against
telemetry_metrics behave the same.

inlet_temp_c/outlet_temp_c use real cooling data when the export has a
cooling_cdu.json (see idt4gdc-digital-twins' loadtest/export_sim.py --cooling,
on by default) -- rack_supply_temp/rack_return_temp from RAPS's
SimpleCoolingModel, one system-wide reading per timestamp (idt4gdc systems
are configured num_cdus=1) with a small per-node jitter/bias layered on so
racks aren't perfectly flat in dashboards. Falls back to the fully synthetic
ambient-sine-wave formula when cooling_cdu.json is absent or empty (older
exports, or a sim run with --no-cooling).

The sim's own timeline is replayed compressed (REPLAY_SPEED sim-seconds per
real second) but every row is inserted at wall-clock "now", exactly like
simulator.py's live loop -- that's what makes it show up as live data instead
of backdated history. On exhausting the export it loops back to the start
(LOOP=true) so a long-running container keeps producing fresh-looking data.
"""
import bisect
import json
import math
import os
import random
import sys
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://grafana:grafana@localhost:5432/opsdemo")
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", "/replay-data/current"))
NODE_PDUID_MAP = os.getenv("NODE_PDUID_MAP")  # optional path to node->PDU json (bridge's mapping shape); defaults to <EXPORT_DIR>/node_to_pduid.json if present
RACK_SIZE = int(os.getenv("RACK_SIZE", "32"))  # nodes per synthetic rack when no PDU map is given

ROOM_ID = os.getenv("ROOM_ID", "room-dt")
ROOM_NAME_OVERRIDE = os.getenv("ROOM_NAME")

REPLAY_SPEED = float(os.getenv("REPLAY_SPEED", "20"))  # sim-seconds advanced per real second
LIVE_INTERVAL_SECONDS = int(os.getenv("LIVE_INTERVAL_SECONDS", "10"))
BACKFILL_MINUTES = float(os.getenv("BACKFILL_MINUTES", "20"))
BACKFILL_STEP_SECONDS = int(os.getenv("BACKFILL_STEP_SECONDS", "30"))
LOOP = os.getenv("LOOP", "true").strip().lower() not in ("0", "false", "no")

IDLE_POWER_FRACTION = float(os.getenv("IDLE_POWER_FRACTION", "0.08"))
HEADROOM_FACTOR = float(os.getenv("HEADROOM_FACTOR", "1.35"))  # nominal_power_w = observed peak * this; without headroom, active nodes sit at ~100% of "nominal" and constantly trip the power/cpu alert thresholds. 1.35 puts a fully-active node's cpu proxy around 74%, just under the 75% warning line, so warnings show up on jitter excursions rather than constantly.
STALE_AFTER_S = float(os.getenv("STALE_AFTER_S", "30"))
ASSET_PREFIX = "dt-"


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def node_bias(node_id: str) -> float:
    """Deterministic -1..1 offset per node so replayed assets aren't visually identical."""
    return (zlib.crc32(node_id.encode()) % 1000) / 1000.0 * 2.0 - 1.0


def wait_for_db():
    while True:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        except psycopg2.OperationalError:
            print("Waiting for PostgreSQL...", flush=True)
            time.sleep(2)


class Dataset:
    def __init__(self, export_dir: Path):
        sim = json.loads((export_dir / "sim.json").read_text())
        self.system = sim.get("system", "unknown")

        trace = []
        trace_path = export_dir / "trace.json"
        if trace_path.exists():
            trace = json.loads(trace_path.read_text())
        gpus_by_job = {str(j["job_id"]): j.get("gpus", 0) for j in trace}

        map_path = Path(NODE_PDUID_MAP) if NODE_PDUID_MAP else export_dir / "node_to_pduid.json"
        node_pdu = {}
        if map_path.exists():
            node_pdu = {str(k): str(v) for k, v in json.loads(map_path.read_text()).items()}

        node_points: dict[str, list[tuple[datetime, float]]] = {}
        node_is_gpu: dict[str, bool] = {}

        power_path = export_dir / "job_power_history.jsonl"
        with power_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                nodes = record["nodes"]
                is_gpu = gpus_by_job.get(str(record["job_id"]), 0) > 0
                n = max(len(nodes), 1)
                for point in record["power_history"]:
                    ts = parse_iso(point["timestamp"])
                    per_node = float(point["power_w"]) / n
                    for node in nodes:
                        node_points.setdefault(node, []).append((ts, per_node))
                        if is_gpu:
                            node_is_gpu[node] = True

        if not node_points:
            raise RuntimeError(f"No power-history points found in {power_path}")

        for pts in node_points.values():
            pts.sort(key=lambda p: p[0])

        cooling_path = export_dir / "cooling_cdu.json"
        cooling_points: list[tuple[datetime, float, float]] = []
        if cooling_path.exists():
            cooling_data = json.loads(cooling_path.read_text()).get("data") or []
            by_ts: dict[datetime, list[tuple[float, float]]] = {}
            for point in cooling_data:
                supply = point.get("rack_supply_temp")
                ret = point.get("rack_return_temp")
                if supply is None or ret is None:
                    continue
                by_ts.setdefault(parse_iso(point["timestamp"]), []).append((float(supply), float(ret)))
            # idt4gdc systems run num_cdus=1, so each timestamp normally has one reading;
            # average across CDUs if a system with more than one is ever replayed, rather
            # than assuming which CDU applies to which node (no CDU->node mapping exists).
            cooling_points = sorted(
                (ts, sum(s for s, _ in vals) / len(vals), sum(r for _, r in vals) / len(vals))
                for ts, vals in by_ts.items()
            )
        self.cooling_points = cooling_points
        self.has_cooling = len(cooling_points) > 0

        self.node_points = node_points
        self.node_is_gpu = node_is_gpu
        self.nodes = sorted(node_points.keys())
        self.node_peak = {
            node: max((p for _, p in pts), default=50.0) or 50.0
            for node, pts in node_points.items()
        }
        self.node_nominal = {node: peak * HEADROOM_FACTOR for node, peak in self.node_peak.items()}

        try:
            self.sim_start = parse_iso(sim["start"])
            self.sim_end = parse_iso(sim["end"])
        except KeyError:
            all_ts = [ts for pts in node_points.values() for ts, _ in pts]
            self.sim_start, self.sim_end = min(all_ts), max(all_ts)
        if self.sim_end <= self.sim_start:
            raise RuntimeError(f"Degenerate sim window: {self.sim_start} .. {self.sim_end}")

        self.rack_of: dict[str, str] = {}
        self.rack_name_of: dict[str, str] = {}
        if node_pdu:
            for node in self.nodes:
                pdu = node_pdu.get(node, "UNMAPPED")
                rack_id = f"{ASSET_PREFIX}rack-{pdu.lower().replace(' ', '-')}"
                self.rack_of[node] = rack_id
                self.rack_name_of[rack_id] = pdu
        else:
            for idx, node in enumerate(self.nodes):
                bucket = idx // RACK_SIZE
                rack_id = f"{ASSET_PREFIX}rack-{bucket:02d}"
                self.rack_of[node] = rack_id
                self.rack_name_of[rack_id] = f"DT Rack {bucket + 1:02d}"

    def power_at(self, node: str, ts: datetime) -> tuple[float, bool]:
        """Returns (power_w, active) -- active is False when falling back to idle baseline."""
        points = self.node_points.get(node)
        peak = self.node_peak.get(node, 50.0)
        idle = peak * IDLE_POWER_FRACTION
        if not points:
            return idle, False
        idx = bisect.bisect_right(points, (ts, float("inf"))) - 1
        if idx < 0:
            return idle, False
        pt_ts, pt_power = points[idx]
        if (ts - pt_ts).total_seconds() > STALE_AFTER_S:
            return idle, False
        return pt_power, True

    def cooling_at(self, ts: datetime) -> tuple[float, float] | None:
        """
        Returns (rack_supply_temp, rack_return_temp) from real cooling data, or None if
        the export has none. Unlike power_at, this doesn't gate on staleness -- cooling
        samples are regular system-wide readings at export granularity (typically 60s),
        not per-job events, so the nearest sample is always a reasonable read. Clamps to
        the first sample for timestamps before the sim's first cooling tick (e.g. during
        backfill, whose wall-clock "now" precedes sim_cursor).
        """
        if not self.cooling_points:
            return None
        idx = bisect.bisect_right(self.cooling_points, (ts, float("inf"), float("inf"))) - 1
        idx = max(idx, 0)
        _, supply, ret = self.cooling_points[idx]
        return supply, ret


def emission_factor(ts: datetime) -> float:
    hour = ts.hour + ts.minute / 60.0
    renewable_wave = 0.34 + 0.05 * math.sin((hour - 6) / 24 * 2 * math.pi)
    balancing_wave = 0.03 * math.sin((hour * 3) / 24 * 2 * math.pi)
    return max(0.24, min(0.43, renewable_wave + balancing_wave))


def seed_dimensions(conn, dataset: Dataset):
    room_name = ROOM_NAME_OVERRIDE or f"ExaDigiT Replay ({dataset.system})"
    racks = sorted(set(dataset.rack_of.values()))
    rack_node_count = {r: 0 for r in racks}
    for node in dataset.nodes:
        rack_node_count[dataset.rack_of[node]] += 1

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rooms (room_id, room_name) VALUES (%s, %s)
            ON CONFLICT (room_id) DO UPDATE SET room_name = EXCLUDED.room_name
            """,
            (ROOM_ID, room_name),
        )
        cur.executemany(
            """
            INSERT INTO racks (rack_id, room_id, rack_name, capacity_u, power_capacity_w)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (rack_id) DO UPDATE
            SET room_id = EXCLUDED.room_id, rack_name = EXCLUDED.rack_name,
                capacity_u = EXCLUDED.capacity_u, power_capacity_w = EXCLUDED.power_capacity_w
            """,
            [
                (
                    rack_id,
                    ROOM_ID,
                    dataset.rack_name_of[rack_id],
                    max(rack_node_count[rack_id], 1),
                    sum(dataset.node_nominal[n] for n in dataset.nodes if dataset.rack_of[n] == rack_id) * 1.5,
                )
                for rack_id in racks
            ],
        )

        rack_position = {r: 0 for r in racks}
        asset_rows = []
        for node in dataset.nodes:
            rack_id = dataset.rack_of[node]
            rack_position[rack_id] += 1
            asset_rows.append((
                f"{ASSET_PREFIX}{node}",
                node,
                ROOM_ID,
                room_name,
                rack_id,
                dataset.rack_name_of[rack_id],
                "gpu-node" if dataset.node_is_gpu.get(node) else "compute-node",
                rack_position[rack_id],
                1,
                True,
                round(dataset.node_nominal[node], 2),
            ))
        cur.executemany(
            """
            INSERT INTO assets (
                asset_id, asset_name, room_id, room_name, rack_id, rack_name,
                asset_type, u_position, u_height, accessible, nominal_power_w
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (asset_id) DO UPDATE
            SET asset_name = EXCLUDED.asset_name, room_id = EXCLUDED.room_id,
                room_name = EXCLUDED.room_name, rack_id = EXCLUDED.rack_id,
                rack_name = EXCLUDED.rack_name, asset_type = EXCLUDED.asset_type,
                u_position = EXCLUDED.u_position, u_height = EXCLUDED.u_height,
                accessible = EXCLUDED.accessible, nominal_power_w = EXCLUDED.nominal_power_w
            """,
            asset_rows,
        )
    conn.commit()
    print(f"Seeded {len(dataset.nodes)} asset(s) across {len(racks)} rack(s) in room '{room_name}'", flush=True)


def build_row(dataset: Dataset, node: str, ts: datetime, sim_ts: datetime, rng: random.Random):
    power, active = dataset.power_at(node, sim_ts)
    power *= 1.0 + rng.uniform(-0.03, 0.03)
    nominal = dataset.node_nominal[node]

    cpu = max(3.0, min(99.0, 100.0 * power / max(nominal, 1.0)))

    bias = node_bias(node)
    cooling = dataset.cooling_at(sim_ts)
    if cooling is not None:
        # Real SimpleCoolingModel output -- one system-wide reading per timestamp
        # (idt4gdc systems run num_cdus=1), so layer a small per-node jitter/bias on top
        # purely so racks aren't perfectly flat in dashboards; the underlying values are
        # real, not synthesized.
        supply_temp, return_temp = cooling
        inlet = supply_temp + 0.3 * bias + rng.uniform(-0.2, 0.2)
        outlet = return_temp + 0.3 * bias + rng.uniform(-0.2, 0.2)
    else:
        day_fraction = (ts.hour * 60 + ts.minute) / 1440.0
        ambient = 20.5 + 0.8 * math.sin(2 * math.pi * day_fraction) + bias
        inlet = ambient + power / 950.0 + rng.uniform(-0.3, 0.3)
        outlet = inlet + 5.1 + cpu / 18.0 + rng.uniform(-0.4, 0.4)

    ef = emission_factor(ts)
    carbon = (power / 1000.0) * ef

    operational_state = "running"  # replay nodes are always powered/allocatable, never flagged standby/maintenance
    status_level = "normal"
    if cpu >= 90 or outlet >= 36 or power >= nominal * 1.18:
        status_level = "critical"
    elif cpu >= 75 or outlet >= 34 or power >= nominal * 1.08:
        status_level = "warning"

    return (
        ts,
        f"{ASSET_PREFIX}{node}",
        round(cpu, 2),
        round(power, 2),
        round(inlet, 2),
        round(outlet, 2),
        round(ef, 4),
        round(carbon, 4),
        status_level,
        operational_state,
    )


def insert_snapshot(conn, dataset: Dataset, ts: datetime, sim_ts: datetime, rng: random.Random):
    rows = [build_row(dataset, node, ts, sim_ts, rng) for node in dataset.nodes]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO telemetry_metrics (
                ts, asset_id, cpu_usage, power_w, inlet_temp_c, outlet_temp_c,
                emission_factor_kg_per_kwh, carbon_kg, status_level, operational_state
            ) VALUES %s
            ON CONFLICT (ts, asset_id) DO NOTHING
            """,
            rows,
        )
    conn.commit()


def advance_cursor(dataset: Dataset, sim_ts: datetime, delta_seconds: float) -> datetime:
    new_ts = sim_ts + timedelta(seconds=delta_seconds)
    if new_ts > dataset.sim_end:
        if not LOOP:
            return dataset.sim_end
        overflow = (new_ts - dataset.sim_end).total_seconds()
        span = (dataset.sim_end - dataset.sim_start).total_seconds() or 1.0
        overflow %= span
        new_ts = dataset.sim_start + timedelta(seconds=overflow)
        print(f"Replay reached sim end, looping back to {dataset.sim_start.isoformat()}", flush=True)
    return new_ts


def replay_seeded(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM telemetry_metrics WHERE asset_id LIKE %s LIMIT 1", (f"{ASSET_PREFIX}%",))
        return cur.fetchone() is not None


def main():
    if not (EXPORT_DIR / "sim.json").exists():
        print(f"ERROR: no export found at {EXPORT_DIR} (expected sim.json, job_power_history.jsonl)", file=sys.stderr)
        sys.exit(1)

    dataset = Dataset(EXPORT_DIR)
    print(
        f"Loaded export: system={dataset.system} nodes={len(dataset.nodes)} "
        f"window={dataset.sim_start.isoformat()}..{dataset.sim_end.isoformat()} "
        f"cooling={'real (' + str(len(dataset.cooling_points)) + ' pt)' if dataset.has_cooling else 'synthetic'}",
        flush=True,
    )

    rng = random.Random(42)
    conn = wait_for_db()
    conn.autocommit = False
    seed_dimensions(conn, dataset)

    sim_cursor = dataset.sim_start
    if not replay_seeded(conn):
        now0 = datetime.now(timezone.utc).replace(microsecond=0)
        steps = max(int((BACKFILL_MINUTES * 60) // BACKFILL_STEP_SECONDS), 0)
        for i in range(steps, 0, -1):
            ts = now0 - timedelta(seconds=i * BACKFILL_STEP_SECONDS)
            insert_snapshot(conn, dataset, ts, sim_cursor, rng)
            sim_cursor = advance_cursor(dataset, sim_cursor, REPLAY_SPEED * BACKFILL_STEP_SECONDS)
        print(f"Backfilled {steps} step(s) covering {BACKFILL_MINUTES:.0f} minute(s)", flush=True)
    else:
        print("Existing dt- telemetry found, skipping backfill; starting a fresh pass at sim start", flush=True)

    while True:
        try:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            insert_snapshot(conn, dataset, now, sim_cursor, rng)
            sim_cursor = advance_cursor(dataset, sim_cursor, REPLAY_SPEED * LIVE_INTERVAL_SECONDS)
            time.sleep(LIVE_INTERVAL_SECONDS)
        except psycopg2.Error as e:
            print(f"DB error, reconnecting: {e}", file=sys.stderr)
            conn.close()
            time.sleep(2)
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False


if __name__ == "__main__":
    main()
