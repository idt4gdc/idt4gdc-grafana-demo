import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://grafana:grafana@localhost:5432/opsdemo")
SEED_HOURS = int(os.getenv("SEED_HOURS", "24"))
HISTORY_STEP_SECONDS = int(os.getenv("HISTORY_STEP_SECONDS", "300"))
LIVE_INTERVAL_SECONDS = int(os.getenv("LIVE_INTERVAL_SECONDS", "10"))


@dataclass(frozen=True)
class AssetBlueprint:
    asset_id: str
    asset_name: str
    room_id: str
    room_name: str
    rack_id: str
    rack_name: str
    asset_type: str
    u_position: int
    u_height: int
    accessible: bool
    nominal_power_w: float
    cpu_baseline: float
    cpu_spread: float
    thermal_bias: float
    risk_bias: float


ROOMS = [
    ("room-a", "Room-A Pilot Hall"),
    ("room-b", "Room-B Expansion Hall"),
]

RACKS = [
    ("rack-01", "room-a", "Rack-01", 42, 3600),
    ("rack-02", "room-a", "Rack-02", 42, 4200),
    ("rack-03", "room-a", "Rack-03", 42, 3900),
    ("rack-04", "room-b", "Rack-04", 42, 3600),
    ("rack-05", "room-b", "Rack-05", 42, 4300),
    ("rack-06", "room-b", "Rack-06", 42, 3800),
]

ASSETS = [
    AssetBlueprint("srv-01", "Srv-01", "room-a", "Room-A Pilot Hall", "rack-01", "Rack-01", "compute-node", 38, 2, True, 410, 52, 14, 0.4, 0.2),
    AssetBlueprint("srv-02", "Srv-02", "room-a", "Room-A Pilot Hall", "rack-01", "Rack-01", "compute-node", 34, 2, True, 430, 58, 16, 0.8, 0.5),
    AssetBlueprint("srv-03", "Srv-03", "room-a", "Room-A Pilot Hall", "rack-01", "Rack-01", "storage-node", 28, 4, True, 360, 34, 10, -0.2, 0.1),
    AssetBlueprint("srv-04", "Srv-04", "room-a", "Room-A Pilot Hall", "rack-01", "Rack-01", "gpu-node", 20, 6, True, 620, 69, 18, 1.4, 0.8),
    AssetBlueprint("srv-05", "Srv-05", "room-a", "Room-A Pilot Hall", "rack-02", "Rack-02", "compute-node", 38, 2, True, 405, 48, 15, 0.2, 0.1),
    AssetBlueprint("srv-06", "Srv-06", "room-a", "Room-A Pilot Hall", "rack-02", "Rack-02", "compute-node", 34, 2, True, 425, 57, 13, 0.5, 0.2),
    AssetBlueprint("srv-07", "Srv-07", "room-a", "Room-A Pilot Hall", "rack-02", "Rack-02", "gpu-node", 24, 6, True, 640, 74, 17, 1.6, 1.0),
    AssetBlueprint("srv-08", "Srv-08", "room-a", "Room-A Pilot Hall", "rack-02", "Rack-02", "storage-node", 16, 4, False, 340, 31, 9, -0.1, 0.0),
    AssetBlueprint("srv-09", "Srv-09", "room-a", "Room-A Pilot Hall", "rack-03", "Rack-03", "compute-node", 38, 2, True, 395, 46, 14, 0.1, 0.2),
    AssetBlueprint("srv-10", "Srv-10", "room-a", "Room-A Pilot Hall", "rack-03", "Rack-03", "compute-node", 34, 2, True, 420, 54, 16, 0.6, 0.4),
    AssetBlueprint("srv-11", "Srv-11", "room-a", "Room-A Pilot Hall", "rack-03", "Rack-03", "gpu-node", 22, 6, True, 650, 76, 18, 1.8, 1.2),
    AssetBlueprint("srv-12", "Srv-12", "room-a", "Room-A Pilot Hall", "rack-03", "Rack-03", "storage-node", 12, 4, False, 330, 30, 8, -0.3, 0.1),
    AssetBlueprint("srv-13", "Srv-13", "room-b", "Room-B Expansion Hall", "rack-04", "Rack-04", "compute-node", 38, 2, True, 400, 49, 14, 0.2, 0.2),
    AssetBlueprint("srv-14", "Srv-14", "room-b", "Room-B Expansion Hall", "rack-04", "Rack-04", "compute-node", 34, 2, True, 415, 53, 16, 0.4, 0.3),
    AssetBlueprint("srv-15", "Srv-15", "room-b", "Room-B Expansion Hall", "rack-04", "Rack-04", "storage-node", 28, 4, True, 345, 33, 9, 0.0, 0.0),
    AssetBlueprint("srv-16", "Srv-16", "room-b", "Room-B Expansion Hall", "rack-04", "Rack-04", "gpu-node", 18, 6, True, 610, 68, 18, 1.1, 0.7),
    AssetBlueprint("srv-17", "Srv-17", "room-b", "Room-B Expansion Hall", "rack-05", "Rack-05", "compute-node", 38, 2, True, 405, 50, 14, 0.2, 0.3),
    AssetBlueprint("srv-18", "Srv-18", "room-b", "Room-B Expansion Hall", "rack-05", "Rack-05", "compute-node", 34, 2, True, 430, 56, 15, 0.6, 0.4),
    AssetBlueprint("srv-19", "Srv-19", "room-b", "Room-B Expansion Hall", "rack-05", "Rack-05", "gpu-node", 24, 6, True, 660, 77, 18, 1.7, 1.1),
    AssetBlueprint("srv-20", "Srv-20", "room-b", "Room-B Expansion Hall", "rack-05", "Rack-05", "storage-node", 16, 4, False, 335, 30, 8, -0.2, 0.1),
    AssetBlueprint("srv-21", "Srv-21", "room-b", "Room-B Expansion Hall", "rack-06", "Rack-06", "compute-node", 38, 2, True, 390, 47, 14, 0.1, 0.2),
    AssetBlueprint("srv-22", "Srv-22", "room-b", "Room-B Expansion Hall", "rack-06", "Rack-06", "compute-node", 34, 2, True, 410, 52, 15, 0.3, 0.2),
    AssetBlueprint("srv-23", "Srv-23", "room-b", "Room-B Expansion Hall", "rack-06", "Rack-06", "storage-node", 28, 4, True, 350, 34, 9, 0.1, 0.1),
    AssetBlueprint("srv-24", "Srv-24", "room-b", "Room-B Expansion Hall", "rack-06", "Rack-06", "gpu-node", 20, 6, True, 630, 72, 17, 1.2, 0.9),
]


def connect():
    return psycopg2.connect(DATABASE_URL)


def wait_for_db():
    while True:
        try:
            conn = connect()
            conn.close()
            return
        except psycopg2.OperationalError:
            print("Waiting for PostgreSQL...")
            time.sleep(2)


def seed_dimensions(conn):
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO rooms (room_id, room_name)
            VALUES (%s, %s)
            ON CONFLICT (room_id) DO UPDATE
            SET room_name = EXCLUDED.room_name
            """,
            ROOMS,
        )
        cur.executemany(
            """
            INSERT INTO racks (rack_id, room_id, rack_name, capacity_u, power_capacity_w)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (rack_id) DO UPDATE
            SET room_id = EXCLUDED.room_id,
                rack_name = EXCLUDED.rack_name,
                capacity_u = EXCLUDED.capacity_u,
                power_capacity_w = EXCLUDED.power_capacity_w
            """,
            RACKS,
        )
        cur.executemany(
            """
            INSERT INTO assets (
                asset_id, asset_name, room_id, room_name, rack_id, rack_name,
                asset_type, u_position, u_height, accessible, nominal_power_w
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (asset_id) DO UPDATE
            SET asset_name = EXCLUDED.asset_name,
                room_id = EXCLUDED.room_id,
                room_name = EXCLUDED.room_name,
                rack_id = EXCLUDED.rack_id,
                rack_name = EXCLUDED.rack_name,
                asset_type = EXCLUDED.asset_type,
                u_position = EXCLUDED.u_position,
                u_height = EXCLUDED.u_height,
                accessible = EXCLUDED.accessible,
                nominal_power_w = EXCLUDED.nominal_power_w
            """,
            [
                (
                    asset.asset_id,
                    asset.asset_name,
                    asset.room_id,
                    asset.room_name,
                    asset.rack_id,
                    asset.rack_name,
                    asset.asset_type,
                    asset.u_position,
                    asset.u_height,
                    asset.accessible,
                    asset.nominal_power_w,
                )
                for asset in ASSETS
            ],
        )
    conn.commit()


def telemetry_count(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM telemetry_metrics")
        return cur.fetchone()[0]


def latest_timestamp(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(ts) FROM telemetry_metrics")
        return cur.fetchone()[0]


def emission_factor(ts):
    hour = ts.hour + (ts.minute / 60.0)
    renewable_wave = 0.34 + 0.05 * math.sin((hour - 6) / 24 * 2 * math.pi)
    balancing_wave = 0.03 * math.sin((hour * 3) / 24 * 2 * math.pi)
    return max(0.24, min(0.43, renewable_wave + balancing_wave))


def simulate_metrics(asset, ts, rng):
    minute_of_day = ts.hour * 60 + ts.minute
    day_fraction = minute_of_day / 1440.0
    room_phase = 0.0 if asset.room_id == "room-a" else 0.65
    rack_phase = int(asset.rack_id[-2:]) * 0.12
    business_cycle = 0.55 + 0.20 * math.sin(2 * math.pi * day_fraction - 1.3)
    batch_cycle = 0.10 * math.sin(4 * math.pi * day_fraction + rack_phase)
    rack_pressure = 0.08 * math.sin(7 * math.pi * day_fraction + room_phase + rack_phase)
    burst = 0.0
    if asset.asset_type == "gpu-node":
        burst = 0.18 * max(0.0, math.sin(6 * math.pi * day_fraction + 0.5))
    elif asset.asset_type == "storage-node":
        burst = 0.05 * math.cos(5 * math.pi * day_fraction + rack_phase)

    noise = rng.uniform(-0.05, 0.05)
    cpu_ratio = business_cycle + batch_cycle + rack_pressure + burst + noise + asset.risk_bias * 0.03
    cpu = asset.cpu_baseline + asset.cpu_spread * (cpu_ratio * 3.2)
    cpu = max(8.0, min(99.0, cpu))

    maintenance_window = asset.asset_id in {"srv-08", "srv-20"} and 120 <= minute_of_day % 360 <= 150
    standby_window = asset.asset_id in {"srv-03", "srv-12", "srv-15"} and 15 <= minute_of_day % 180 <= 35

    operational_state = "running"
    if maintenance_window:
        operational_state = "maintenance"
        cpu *= 0.25
    elif standby_window:
        operational_state = "standby"
        cpu *= 0.45

    power = asset.nominal_power_w * (0.36 + cpu / 135.0)
    power *= 1.0 + rng.uniform(-0.03, 0.03)
    if asset.asset_type == "gpu-node":
        power *= 1.08
    if operational_state == "maintenance":
        power *= 0.55
    if operational_state == "standby":
        power *= 0.72

    ambient = 20.5 + 0.8 * math.sin(2 * math.pi * day_fraction + room_phase)
    inlet = ambient + asset.thermal_bias + power / 950.0 + rng.uniform(-0.3, 0.3)
    outlet = inlet + 5.1 + cpu / 18.0 + rng.uniform(-0.4, 0.4)

    ef = emission_factor(ts)
    carbon = (power / 1000.0) * ef

    status_level = "normal"
    if cpu >= 90 or outlet >= 36 or power >= asset.nominal_power_w * 1.18:
        status_level = "critical"
    elif cpu >= 75 or outlet >= 34 or power >= asset.nominal_power_w * 1.08 or operational_state != "running":
        status_level = "warning"

    return (
        ts,
        asset.asset_id,
        round(cpu, 2),
        round(power, 2),
        round(inlet, 2),
        round(outlet, 2),
        round(ef, 4),
        round(carbon, 4),
        status_level,
        operational_state,
    )


def insert_snapshot(conn, ts, rng):
    rows = [simulate_metrics(asset, ts, rng) for asset in ASSETS]
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


def seed_history(conn, rng):
    if telemetry_count(conn) > 0:
        return
    end_ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_ts = end_ts - timedelta(hours=SEED_HOURS)
    current = start_ts
    while current <= end_ts:
        insert_snapshot(conn, current, rng)
        current += timedelta(seconds=HISTORY_STEP_SECONDS)


def main():
    wait_for_db()
    rng = random.Random(42)
    conn = connect()
    conn.autocommit = False
    seed_dimensions(conn)
    seed_history(conn, rng)

    while True:
        try:
            latest = latest_timestamp(conn)
            now_ts = datetime.now(timezone.utc).replace(microsecond=0)
            if latest is None or latest < now_ts:
                insert_snapshot(conn, now_ts, rng)
            time.sleep(LIVE_INTERVAL_SECONDS)
        except psycopg2.Error:
            conn.close()
            time.sleep(2)
            conn = connect()
            conn.autocommit = False


if __name__ == "__main__":
    main()

