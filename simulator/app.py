import math
import os
import random
import time
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://grafana:grafana@localhost:5432/opsdemo")
SEED_HOURS = int(os.getenv("SEED_HOURS", "24"))
HISTORY_STEP_SECONDS = int(os.getenv("HISTORY_STEP_SECONDS", "300"))
LIVE_INTERVAL_SECONDS = int(os.getenv("LIVE_INTERVAL_SECONDS", "10"))
AI_MODEL_RESULTS_PATH = Path(__file__).resolve().parent / "data" / "ai_model_results.json"
SUSTAINABILITY_KPI_PATH = Path(__file__).resolve().parent / "data" / "sustainability_kpis.json"
DATA_CENTRES_PATH = Path(__file__).resolve().parent / "data" / "data_centres.json"
GPU_FPGA_PATH = Path(__file__).resolve().parent / "data" / "gpu_fpga_acceleration.json"


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


def load_ai_model_results():
    return json.loads(AI_MODEL_RESULTS_PATH.read_text(encoding="utf-8"))


def load_sustainability_kpis():
    return json.loads(SUSTAINABILITY_KPI_PATH.read_text(encoding="utf-8"))


def load_data_centres():
    return json.loads(DATA_CENTRES_PATH.read_text(encoding="utf-8"))


def load_gpu_fpga_data():
    return json.loads(GPU_FPGA_PATH.read_text(encoding="utf-8"))


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


def seed_ai_model_data(conn):
    ai_data = load_ai_model_results()
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO ai_model_results (
                model_name, model_type, purpose, energy_j, accuracy_percent,
                interpretation, best_model, preferred_family
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (model_name) DO UPDATE
            SET model_type = EXCLUDED.model_type,
                purpose = EXCLUDED.purpose,
                energy_j = EXCLUDED.energy_j,
                accuracy_percent = EXCLUDED.accuracy_percent,
                interpretation = EXCLUDED.interpretation,
                best_model = EXCLUDED.best_model,
                preferred_family = EXCLUDED.preferred_family
            """,
            [
                (
                    model["name"],
                    model["type"],
                    model["purpose"],
                    model.get("energy_j"),
                    model.get("accuracy_percent"),
                    model["interpretation"],
                    model.get("best_model", False),
                    model.get("preferred_family", False),
                )
                for model in ai_data["models"]
            ],
        )
        cur.executemany(
            """
            INSERT INTO ai_model_features (feature_name, description, display_order)
            VALUES (%s, %s, %s)
            ON CONFLICT (feature_name) DO UPDATE
            SET description = EXCLUDED.description,
                display_order = EXCLUDED.display_order
            """,
            [
                (feature["name"], feature["description"], idx)
                for idx, feature in enumerate(ai_data["features"], start=1)
            ],
        )
        cur.executemany(
            """
            INSERT INTO ai_feature_importance (model_name, feature_name, importance_score)
            VALUES (%s, %s, %s)
            ON CONFLICT (model_name, feature_name) DO UPDATE
            SET importance_score = EXCLUDED.importance_score
            """,
            [
                (
                    item["model_name"],
                    item["feature_name"],
                    item["importance_score"],
                )
                for item in ai_data["feature_importance"]
            ],
        )
    conn.commit()


def seed_sustainability_kpi_data(conn):
    sustainability_data = load_sustainability_kpis()
    config = sustainability_data["config"]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sustainability_kpi_config (
                profile_name,
                facility_overhead_base,
                facility_overhead_wave,
                renewable_fraction_base,
                renewable_fraction_wave,
                reused_energy_fraction_base,
                reused_energy_fraction_wave,
                baseline_co2_multiplier,
                performance_factor,
                cue_it_energy_share,
                hue_base,
                she_base,
                apcren_base,
                dca_base
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (profile_name) DO UPDATE
            SET facility_overhead_base = EXCLUDED.facility_overhead_base,
                facility_overhead_wave = EXCLUDED.facility_overhead_wave,
                renewable_fraction_base = EXCLUDED.renewable_fraction_base,
                renewable_fraction_wave = EXCLUDED.renewable_fraction_wave,
                reused_energy_fraction_base = EXCLUDED.reused_energy_fraction_base,
                reused_energy_fraction_wave = EXCLUDED.reused_energy_fraction_wave,
                baseline_co2_multiplier = EXCLUDED.baseline_co2_multiplier,
                performance_factor = EXCLUDED.performance_factor,
                cue_it_energy_share = EXCLUDED.cue_it_energy_share,
                hue_base = EXCLUDED.hue_base,
                she_base = EXCLUDED.she_base,
                apcren_base = EXCLUDED.apcren_base,
                dca_base = EXCLUDED.dca_base
            """,
            (
                sustainability_data["profile_name"],
                config["facility_overhead_base"],
                config["facility_overhead_wave"],
                config["renewable_fraction_base"],
                config["renewable_fraction_wave"],
                config["reused_energy_fraction_base"],
                config["reused_energy_fraction_wave"],
                config["baseline_co2_multiplier"],
                config["performance_factor"],
                config["cue_it_energy_share"],
                config["hue_base"],
                config["she_base"],
                config["apcren_base"],
                config["dca_base"],
            ),
        )
        cur.executemany(
            """
            INSERT INTO sustainability_kpi_metadata (
                kpi_key, label, direction, interpretation, is_advanced, display_order
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (kpi_key) DO UPDATE
            SET label = EXCLUDED.label,
                direction = EXCLUDED.direction,
                interpretation = EXCLUDED.interpretation,
                is_advanced = EXCLUDED.is_advanced,
                display_order = EXCLUDED.display_order
            """,
            [
                (
                    kpi["key"],
                    kpi["label"],
                    kpi["direction"],
                    kpi["interpretation"],
                    kpi.get("is_advanced", False),
                    idx,
                )
                for idx, kpi in enumerate(sustainability_data["kpis"], start=1)
            ],
        )
    conn.commit()


def seed_data_centre_sources(conn):
    data = load_data_centres()
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO data_centre_sources (
                dc_key, dc_name, location, ip_address, source_type,
                default_username, default_password, jwt_status, stream_status,
                display_order, user_visible, user_added
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dc_key) DO UPDATE
            SET dc_name = EXCLUDED.dc_name,
                location = EXCLUDED.location,
                ip_address = EXCLUDED.ip_address,
                source_type = EXCLUDED.source_type,
                default_username = EXCLUDED.default_username,
                default_password = EXCLUDED.default_password,
                jwt_status = EXCLUDED.jwt_status,
                stream_status = EXCLUDED.stream_status,
                display_order = EXCLUDED.display_order,
                user_visible = EXCLUDED.user_visible,
                user_added = EXCLUDED.user_added
            """,
            [
                (
                    item["key"],
                    item["name"],
                    item["location"],
                    item["ip_address"],
                    item["source_type"],
                    item["default_username"],
                    item["default_password"],
                    item["jwt_status"],
                    item["stream_status"],
                    item["display_order"],
                    item["user_visible"],
                    item["user_added"],
                )
                for item in data["data_centres"]
            ],
        )
    conn.commit()


def seed_gpu_fpga_data(conn):
    data = load_gpu_fpga_data()
    workload = data["workload"]
    scenario = data["scenario"]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO gpu_fpga_workload (workload_name, model_name, goal)
            VALUES (%s, %s, %s)
            ON CONFLICT (workload_name) DO UPDATE
            SET model_name = EXCLUDED.model_name,
                goal = EXCLUDED.goal
            """,
            (workload["name"], workload["model"], workload["goal"]),
        )
        cur.executemany(
            """
            INSERT INTO gpu_fpga_platform_metrics (
                platform, role_description, training_latency_ms, inference_latency_ms,
                speedup_training, speedup_inference, performance_per_watt, power_w, throughput
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (platform) DO UPDATE
            SET role_description = EXCLUDED.role_description,
                training_latency_ms = EXCLUDED.training_latency_ms,
                inference_latency_ms = EXCLUDED.inference_latency_ms,
                speedup_training = EXCLUDED.speedup_training,
                speedup_inference = EXCLUDED.speedup_inference,
                performance_per_watt = EXCLUDED.performance_per_watt,
                power_w = EXCLUDED.power_w,
                throughput = EXCLUDED.throughput
            """,
            [
                (
                    item["platform"],
                    item["role"],
                    item["training_latency_ms"],
                    item["inference_latency_ms"],
                    item["speedup_training"],
                    item["speedup_inference"],
                    item["performance_per_watt"],
                    item["power_w"],
                    item["throughput"],
                )
                for item in data["platforms"]
            ],
        )
        cur.execute(
            """
            INSERT INTO gpu_fpga_scenario (
                scenario_name, baseline_platform, training_platform, inference_platform,
                baseline_energy_j, optimised_energy_j, baseline_co2_kg, optimised_co2_kg,
                energy_saving_percent, throughput_improvement_percent, fpga_inference_speedup,
                fpga_perf_per_watt, gpu_training_acceleration
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (scenario_name) DO UPDATE
            SET baseline_platform = EXCLUDED.baseline_platform,
                training_platform = EXCLUDED.training_platform,
                inference_platform = EXCLUDED.inference_platform,
                baseline_energy_j = EXCLUDED.baseline_energy_j,
                optimised_energy_j = EXCLUDED.optimised_energy_j,
                baseline_co2_kg = EXCLUDED.baseline_co2_kg,
                optimised_co2_kg = EXCLUDED.optimised_co2_kg,
                energy_saving_percent = EXCLUDED.energy_saving_percent,
                throughput_improvement_percent = EXCLUDED.throughput_improvement_percent,
                fpga_inference_speedup = EXCLUDED.fpga_inference_speedup,
                fpga_perf_per_watt = EXCLUDED.fpga_perf_per_watt,
                gpu_training_acceleration = EXCLUDED.gpu_training_acceleration
            """,
            (
                workload["name"],
                scenario["baseline_platform"],
                scenario["training_platform"],
                scenario["inference_platform"],
                scenario["baseline_energy_j"],
                scenario["optimised_energy_j"],
                scenario["baseline_co2_kg"],
                scenario["optimised_co2_kg"],
                scenario["energy_saving_percent"],
                scenario["throughput_improvement_percent"],
                scenario["fpga_inference_speedup"],
                scenario["fpga_perf_per_watt"],
                scenario["gpu_training_acceleration"],
            ),
        )
    conn.commit()


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def build_sustainability_snapshot(ts, rows, sustainability_data):
    config = sustainability_data["config"]
    day_fraction = (ts.hour * 60 + ts.minute) / 1440.0
    hourly_phase = 2 * math.pi * day_fraction

    it_power_w = sum(row[3] for row in rows)
    avg_cpu = sum(row[2] for row in rows) / len(rows)
    avg_inlet = sum(row[4] for row in rows) / len(rows)
    avg_outlet = sum(row[5] for row in rows) / len(rows)
    avg_ef = sum(row[6] for row in rows) / len(rows)
    warning_pressure = sum(1 for row in rows if row[8] != "normal") / len(rows)

    pue = clamp(
        config["facility_overhead_base"]
        + config["facility_overhead_wave"] * math.sin(hourly_phase - 0.7)
        + 0.012 * max(avg_outlet - 31.0, 0.0)
        + 0.045 * warning_pressure,
        1.12,
        1.68,
    )
    total_facility_power_w = it_power_w * pue

    ref = clamp(
        config["renewable_fraction_base"]
        + config["renewable_fraction_wave"] * math.sin(hourly_phase - 1.1)
        - 0.24 * max(avg_ef - 0.30, 0.0),
        0.18,
        0.88,
    )
    erf = clamp(
        config["reused_energy_fraction_base"]
        + config["reused_energy_fraction_wave"] * math.cos(hourly_phase + 0.35)
        + 0.012 * max(avg_outlet - avg_inlet - 6.0, 0.0),
        0.04,
        0.36,
    )

    total_energy_kwh = total_facility_power_w / 1000.0
    renewable_energy_kwh = total_energy_kwh * ref
    reused_energy_kwh = total_energy_kwh * erf
    total_co2_kg = total_energy_kwh * avg_ef
    baseline_co2_kg = total_co2_kg * config["baseline_co2_multiplier"]
    co2_savings_kg = baseline_co2_kg - total_co2_kg

    performance_score = (
        sum(row[2] for row in rows) * config["performance_factor"] * (0.92 + ref * 0.18)
    )
    ppw = performance_score / max(total_facility_power_w, 1.0)
    cue = total_co2_kg / max((it_power_w / 1000.0) * config["cue_it_energy_share"], 0.001)
    cef = total_co2_kg / max(total_energy_kwh, 0.001)

    hue = clamp(
        config["hue_base"]
        + 0.52 * erf
        + 0.04 * math.sin(hourly_phase + 0.9)
        - 0.03 * warning_pressure,
        0.45,
        1.05,
    )
    she = clamp(
        config["she_base"]
        + 0.38 * ref
        + 0.24 * erf
        + 0.03 * math.cos(hourly_phase - 0.4),
        0.35,
        1.0,
    )
    apcren = clamp(
        config["apcren_base"]
        + 0.44 * ref
        - 0.08 * warning_pressure
        + 0.03 * math.sin(hourly_phase * 2.0),
        0.30,
        1.0,
    )
    dca = clamp(
        config["dca_base"]
        + 0.24 * ref
        + 0.10 * erf
        + 0.16 * clamp((1.55 - pue) / 0.45, 0.0, 1.0)
        - 0.08 * warning_pressure,
        0.30,
        1.0,
    )

    return (
        ts,
        round(total_facility_power_w, 2),
        round(it_power_w, 2),
        round(total_energy_kwh, 4),
        round(renewable_energy_kwh, 4),
        round(reused_energy_kwh, 4),
        round(total_co2_kg, 4),
        round(baseline_co2_kg, 4),
        round(performance_score, 2),
        round(it_power_w / 1000.0, 4),
        round(pue, 3),
        round(ref, 3),
        round(erf, 3),
        round(cef, 3),
        round(co2_savings_kg, 4),
        round(ppw, 3),
        round(cue, 3),
        round(hue, 3),
        round(she, 3),
        round(apcren, 3),
        round(dca, 3),
    )


def insert_sustainability_snapshot(conn, ts, rows, sustainability_data):
    snapshot = build_sustainability_snapshot(ts, rows, sustainability_data)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sustainability_kpi_snapshots (
                ts,
                total_facility_power_w,
                it_power_w,
                total_energy_kwh,
                renewable_energy_kwh,
                reused_energy_kwh,
                total_co2_kg,
                baseline_co2_kg,
                performance_score,
                it_energy_kwh,
                pue,
                ref,
                erf,
                cef,
                co2_savings_kg,
                ppw,
                cue,
                hue,
                she,
                apcren,
                dca
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ts) DO UPDATE
            SET total_facility_power_w = EXCLUDED.total_facility_power_w,
                it_power_w = EXCLUDED.it_power_w,
                total_energy_kwh = EXCLUDED.total_energy_kwh,
                renewable_energy_kwh = EXCLUDED.renewable_energy_kwh,
                reused_energy_kwh = EXCLUDED.reused_energy_kwh,
                total_co2_kg = EXCLUDED.total_co2_kg,
                baseline_co2_kg = EXCLUDED.baseline_co2_kg,
                performance_score = EXCLUDED.performance_score,
                it_energy_kwh = EXCLUDED.it_energy_kwh,
                pue = EXCLUDED.pue,
                ref = EXCLUDED.ref,
                erf = EXCLUDED.erf,
                cef = EXCLUDED.cef,
                co2_savings_kg = EXCLUDED.co2_savings_kg,
                ppw = EXCLUDED.ppw,
                cue = EXCLUDED.cue,
                hue = EXCLUDED.hue,
                she = EXCLUDED.she,
                apcren = EXCLUDED.apcren,
                dca = EXCLUDED.dca
            """,
            snapshot,
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
    return rows


def seed_history(conn, rng, sustainability_data):
    if telemetry_count(conn) > 0:
        return
    end_ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_ts = end_ts - timedelta(hours=SEED_HOURS)
    current = start_ts
    while current <= end_ts:
        rows = insert_snapshot(conn, current, rng)
        insert_sustainability_snapshot(conn, current, rows, sustainability_data)
        current += timedelta(seconds=HISTORY_STEP_SECONDS)


def main():
    wait_for_db()
    rng = random.Random(42)
    sustainability_data = load_sustainability_kpis()
    conn = connect()
    conn.autocommit = False
    seed_dimensions(conn)
    seed_ai_model_data(conn)
    seed_data_centre_sources(conn)
    seed_gpu_fpga_data(conn)
    seed_sustainability_kpi_data(conn)
    seed_history(conn, rng, sustainability_data)

    while True:
        try:
            latest = latest_timestamp(conn)
            now_ts = datetime.now(timezone.utc).replace(microsecond=0)
            if latest is None or latest < now_ts:
                rows = insert_snapshot(conn, now_ts, rng)
                insert_sustainability_snapshot(conn, now_ts, rows, sustainability_data)
            time.sleep(LIVE_INTERVAL_SECONDS)
        except psycopg2.Error:
            conn.close()
            time.sleep(2)
            conn = connect()
            conn.autocommit = False


if __name__ == "__main__":
    main()
