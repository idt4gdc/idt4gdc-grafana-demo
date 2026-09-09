"""
Carbon-aware job scheduler service.

Grid data fetch policy:
  - Carbon intensity (NESO): fetched on every scheduled 30-min run.
  - Electricity prices (Octopus Agile): fetched once daily, after 17:30 UTC
    when the following day's half-hourly prices are published.
  - Job-submission triggers: re-solve only — no API calls, uses whatever
    grid data is already stored in the DB.

Confirmation: jobs starting within the next CONFIRMATION_SLOTS half-hour
slots are locked (status='confirmed') and not rescheduled on later runs.
"""
import copy
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import Body, FastAPI, HTTPException
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from model import schedule_jobs
from data.carbon_intensity import get_intensity_data
from data.energy_prices import get_tariff_rates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://grafana:grafana@localhost:5432/opsdemo")
CONFIRMATION_SLOTS = int(os.getenv("CONFIRMATION_SLOTS", "2"))
SLOT_MINUTES = 30
TOTAL_SLOTS = 48  # 24-hour horizon

# available_cpus/available_gpus are node counts (not core/chip counts), matching
# idt4gdc-digital-twins' demonstration-sites table and each system's RAPS config
# (exadigit/exadigit/raps/config/idt4gdc_dc{1,2,3,4}.yaml): nodes_per_rack=32,
# split into gpu_racks vs the remaining CPU racks. dc3=Reading (56 racks, 14 GPU),
# dc1=Edinburgh (16 racks, 4 GPU), dc2=London (12 racks, 3 GPU),
# dc4=Peterborough (6 racks, 1 GPU).
DATA_CENTRES = json.loads(os.getenv("DATA_CENTRES", json.dumps([
    {"name": "Reading",      "ss_id": 3625,  "postcode": "RG31", "dno_region": "J", "available_cpus": 1344, "available_gpus": 448},
    {"name": "Peterborough", "ss_id": 10006, "postcode": "PE2",  "dno_region": "A", "available_cpus": 160,  "available_gpus": 32},
    {"name": "London",       "ss_id": 22794, "postcode": "UB2",  "dno_region": "C", "available_cpus": 288,  "available_gpus": 96},
    {"name": "Edinburgh",    "ss_id": 27152, "postcode": "EH14", "dno_region": "N", "available_cpus": 384,  "available_gpus": 128},
])))

_trigger = threading.Event()
_last_price_fetch: Optional[datetime] = None  # timestamp of last successful price fetch

DEMO_BATCH_PATH = Path(__file__).parent / "demo_job_batch.json"
try:
    _demo_batch_example = json.loads(DEMO_BATCH_PATH.read_text())
except FileNotFoundError:
    _demo_batch_example = []


# ── DB ────────────────────────────────────────────────────────────────────────

def wait_for_db() -> None:
    while True:
        try:
            psycopg2.connect(DATABASE_URL).close()
            log.info("Database connected")
            return
        except psycopg2.OperationalError:
            log.info("Waiting for database...")
            time.sleep(3)


def new_conn():
    return psycopg2.connect(DATABASE_URL)


# ── Time ──────────────────────────────────────────────────────────────────────

def horizon_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(minute=(now.minute // SLOT_MINUTES) * SLOT_MINUTES, second=0, microsecond=0)


# ── Grid data ─────────────────────────────────────────────────────────────────

def _should_fetch_prices() -> bool:
    """True on first run, or once per day after 17:30 UTC (once tomorrow's prices are published)."""
    if _last_price_fetch is None:
        return True  # startup — fetch whatever is available
    now = datetime.now(timezone.utc)
    cutoff = now.replace(hour=17, minute=30, second=0, microsecond=0)
    if now < cutoff:
        return False  # today's post-cutoff refresh hasn't opened yet
    return _last_price_fetch < cutoff  # fetch once per day, after the cutoff


def _fetch_ci(postcode: str, h: datetime) -> list[int]:
    try:
        resp = get_intensity_data(h.strftime('%Y-%m-%dT%H:%MZ'), postcode)
        slots = [entry['intensity']['forecast'] for entry in resp['data']['data']]
        return (slots + [200] * TOTAL_SLOTS)[:TOTAL_SLOTS]
    except Exception as exc:
        log.warning("CI fetch failed for %s: %s", postcode, exc)
        return [200] * TOTAL_SLOTS


def _fetch_price(dno_region: str) -> list[int]:
    try:
        df = get_tariff_rates(dno_region)
        prices = [round(float(p)) for p in df.sort_values('from')['price_p_per_kwh']]
        return (prices + [15] * TOTAL_SLOTS)[:TOTAL_SLOTS]
    except Exception as exc:
        log.warning("Price fetch failed for region %s: %s", dno_region, exc)
        return [15] * TOTAL_SLOTS


def _load_prices_from_db(conn, h: datetime, dc_name: str) -> list[int]:
    """Load stored half-hourly prices for a DC starting from horizon h."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT electricity_price_p FROM grid_forecasts
            WHERE data_centre = %s AND ts >= %s
            ORDER BY ts LIMIT %s
        """, (dc_name, h, TOTAL_SLOTS))
        prices = [int(row[0]) for row in cur.fetchall()]
    return (prices + [15] * TOTAL_SLOTS)[:TOTAL_SLOTS]


def _load_grid_from_db(conn, h: datetime) -> Optional[list[dict]]:
    """Load all grid forecast data from DB for the solver, starting at h."""
    dc_data: dict[str, dict] = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT data_centre, carbon_intensity_g_per_kwh, electricity_price_p
            FROM grid_forecasts WHERE ts >= %s ORDER BY data_centre, ts
        """, (h,))
        for dc_name, ci, price in cur.fetchall():
            if dc_name not in dc_data:
                dc_data[dc_name] = {'ci': [], 'price': []}
            dc_data[dc_name]['ci'].append(int(ci))
            dc_data[dc_name]['price'].append(int(price))

    if not dc_data:
        return None

    dcs = []
    for cfg in DATA_CENTRES:
        data = dc_data.get(cfg['name'], {'ci': [], 'price': []})
        dcs.append({
            **cfg,
            'forecasted_ci':    (data['ci']    + [200] * TOTAL_SLOTS)[:TOTAL_SLOTS],
            'forecasted_price': (data['price'] + [15]  * TOTAL_SLOTS)[:TOTAL_SLOTS],
        })
    return dcs


def _store_grid(conn, dcs: list, h: datetime) -> None:
    rows = [
        (h + timedelta(minutes=i * SLOT_MINUTES), dc['name'],
         dc['forecasted_ci'][i], dc['forecasted_price'][i])
        for dc in dcs
        for i in range(TOTAL_SLOTS)
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO grid_forecasts (ts, data_centre, carbon_intensity_g_per_kwh, electricity_price_p)
            VALUES %s
            ON CONFLICT (ts, data_centre) DO UPDATE SET
                carbon_intensity_g_per_kwh = EXCLUDED.carbon_intensity_g_per_kwh,
                electricity_price_p        = EXCLUDED.electricity_price_p
        """, rows)
    conn.commit()


# ── Job loading ───────────────────────────────────────────────────────────────

def _load_jobs(conn, dcs: list, h: datetime) -> list[dict]:
    dc_names = [dc['name'] for dc in dcs]
    now = datetime.now(timezone.utc)
    jobs = []

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        # Confirmed jobs — pinned to their existing DC + slot
        cur.execute("""
            SELECT sj.job_submission_id AS id, sj.start_time, sj.end_time,
                   sj.data_centre_name, sj.duration_slots,
                   js.job_type, js.resource_count, js.priority, js.carbon_weight, js.cost_weight
            FROM scheduled_jobs sj
            JOIN job_submissions js ON js.id = sj.job_submission_id
            WHERE sj.status = 'confirmed'
        """)
        for row in cur.fetchall():
            end_t = row['end_time']
            if end_t.tzinfo is None:
                end_t = end_t.replace(tzinfo=timezone.utc)
            if end_t <= now:
                with conn.cursor() as c2:
                    c2.execute("UPDATE scheduled_jobs SET status='completed' WHERE job_submission_id=%s", (row['id'],))
                    c2.execute("UPDATE job_submissions SET status='completed' WHERE id=%s", (row['id'],))
                conn.commit()
                continue

            st = row['start_time']
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            slot = round((st - h).total_seconds() / (SLOT_MINUTES * 60))
            if not (0 <= slot < TOTAL_SLOTS):
                continue
            dc_idx = dc_names.index(row['data_centre_name']) if row['data_centre_name'] in dc_names else None
            if dc_idx is None:
                continue

            dur = row['duration_slots']
            jobs.append({
                'id': row['id'], 'duration_slots': dur,
                'solver_spec': {
                    'mode': row['job_type'],
                    'int_cycles':     dur if row['job_type'] == 'CPU' else 1,
                    'float_cycles':   dur if row['job_type'] == 'GPU' else 1,
                    'resource_count': int(row['resource_count']),
                    'priority':       int(row['priority']),
                    'carbon_weight':  int(row['carbon_weight']),
                    'cost_weight':    int(row['cost_weight']),
                    'data_centre':    dc_idx,
                    'start_time':     slot,
                }
            })

        # Pending + unconfirmed scheduled — free to be (re)assigned
        cur.execute("""
            SELECT id, job_type, duration_slots, resource_count, priority,
                   carbon_weight, cost_weight, window_start, window_end
            FROM job_submissions
            WHERE status IN ('pending', 'scheduled')
        """)
        for row in cur.fetchall():
            dur = row['duration_slots']
            spec = {
                'mode': row['job_type'],
                'int_cycles':     dur if row['job_type'] == 'CPU' else 1,
                'float_cycles':   dur if row['job_type'] == 'GPU' else 1,
                'resource_count': int(row['resource_count']),
                'priority':       int(row['priority']),
                'carbon_weight':  int(row['carbon_weight']),
                'cost_weight':    int(row['cost_weight']),
            }
            for key, col in (('window_start', 'window_start'), ('window_end', 'window_end')):
                val = row[col]
                if val is not None:
                    if val.tzinfo is None:
                        val = val.replace(tzinfo=timezone.utc)
                    s = round((val - h).total_seconds() / (SLOT_MINUTES * 60))
                    if 0 <= s < TOTAL_SLOTS:
                        spec[key] = s
            jobs.append({'id': row['id'], 'duration_slots': dur, 'solver_spec': spec})

    return jobs


# ── Core scheduler ────────────────────────────────────────────────────────────

def run_scheduler_once(fetch_grid: bool = True) -> None:
    global _last_price_fetch
    h = horizon_start()

    conn = new_conn()
    try:
        if fetch_grid:
            fetch_prices = _should_fetch_prices()
            log.info("Scheduler run — horizon %s (fetch prices: %s)", h.isoformat(), fetch_prices)
            dcs = []
            for cfg in DATA_CENTRES:
                prices = _fetch_price(cfg['dno_region']) if fetch_prices else _load_prices_from_db(conn, h, cfg['name'])
                dcs.append({
                    **cfg,
                    'forecasted_ci':    _fetch_ci(cfg['postcode'], h),
                    'forecasted_price': prices,
                })
            if fetch_prices:
                _last_price_fetch = datetime.now(timezone.utc)
            _store_grid(conn, dcs, h)
        else:
            log.info("Re-solving from cached grid data — horizon %s", h.isoformat())
            dcs = _load_grid_from_db(conn, h)
            if dcs is None:
                log.warning("No grid data in DB — skipping solve")
                return

        jobs = _load_jobs(conn, dcs, h)
        if not jobs:
            log.info("No jobs in queue")
            return

        log.info("Solving for %d jobs...", len(jobs))
        results = schedule_jobs(dcs, [j['solver_spec'] for j in jobs])
        if results is None:
            log.warning("Solver returned no feasible solution")
            return

        with conn.cursor() as cur:
            for idx, (d, start_slot, _, ci_sum, _, cost_sum, _priority, _mode) in enumerate(results):
                job = jobs[idx]
                start_time = h + timedelta(minutes=start_slot * SLOT_MINUTES)
                end_time   = start_time + timedelta(minutes=job['duration_slots'] * SLOT_MINUTES)
                status     = 'confirmed' if start_slot < CONFIRMATION_SLOTS else 'scheduled'

                cur.execute("""
                    INSERT INTO scheduled_jobs
                        (job_submission_id, scheduled_at, data_centre_name, start_slot,
                         start_time, end_time, duration_slots, carbon_total_g, cost_total_p, status)
                    VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_submission_id) DO UPDATE SET
                        scheduled_at     = EXCLUDED.scheduled_at,
                        data_centre_name = EXCLUDED.data_centre_name,
                        start_slot       = EXCLUDED.start_slot,
                        start_time       = EXCLUDED.start_time,
                        end_time         = EXCLUDED.end_time,
                        duration_slots   = EXCLUDED.duration_slots,
                        carbon_total_g   = EXCLUDED.carbon_total_g,
                        cost_total_p     = EXCLUDED.cost_total_p,
                        status           = EXCLUDED.status
                """, (job['id'], dcs[d]['name'], start_slot, start_time,
                      end_time, job['duration_slots'], ci_sum, float(cost_sum), status))

                cur.execute("UPDATE job_submissions SET status=%s WHERE id=%s", (status, job['id']))

        conn.commit()
        log.info("Scheduled %d jobs", len(results))

    finally:
        conn.close()


def scheduler_loop() -> None:
    while True:
        try:
            run_scheduler_once(fetch_grid=True)
        except Exception:
            log.exception("Scheduler run failed")

        now = datetime.now(timezone.utc)
        next_slot = horizon_start() + timedelta(minutes=SLOT_MINUTES)
        wait = max(10.0, (next_slot - now).total_seconds())
        log.info("Next scheduled grid refresh in %.0fs", wait)

        if _trigger.wait(timeout=wait):
            _trigger.clear()
            log.info("New job submitted — re-solving without grid refresh")
            try:
                run_scheduler_once(fetch_grid=False)
            except Exception:
                log.exception("Triggered solve failed")


# ── FastAPI ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    wait_for_db()
    threading.Thread(target=scheduler_loop, daemon=True).start()
    yield


app = FastAPI(title="iDT4GDC Scheduler", version="1.0", lifespan=lifespan)


class JobRequest(BaseModel):
    label: Optional[str] = None
    job_type: str = "CPU"
    duration_slots: int = 4
    resource_count: int = 1
    priority: int = 5
    carbon_weight: float = 1.0
    cost_weight: float = 1.0
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None


def _validate_job(req: JobRequest) -> None:
    if req.job_type not in ("CPU", "GPU"):
        raise HTTPException(400, "job_type must be 'CPU' or 'GPU'")
    if not (1 <= req.duration_slots <= TOTAL_SLOTS):
        raise HTTPException(400, f"duration_slots must be 1–{TOTAL_SLOTS}")
    if req.resource_count < 1:
        raise HTTPException(400, "resource_count must be >= 1")


def _insert_job(cur, req: JobRequest) -> dict:
    cur.execute("""
        INSERT INTO job_submissions
            (label, job_type, duration_slots, resource_count, priority, carbon_weight, cost_weight, window_start, window_end)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, label, submitted_at, status
    """, (req.label, req.job_type, req.duration_slots, req.resource_count, req.priority,
          req.carbon_weight, req.cost_weight, req.window_start, req.window_end))
    row = cur.fetchone()
    return {"id": row[0], "label": row[1], "submitted_at": row[2].isoformat(), "status": row[3]}


@app.post("/api/jobs", status_code=201)
def submit_job(req: JobRequest):
    _validate_job(req)

    conn = new_conn()
    try:
        with conn.cursor() as cur:
            result = _insert_job(cur, req)
        conn.commit()
    finally:
        conn.close()

    _trigger.set()
    return result


@app.post("/api/jobs/batch", status_code=201)
def submit_jobs_batch(
    reqs: list[JobRequest] = Body(
        ...,
        openapi_examples={
            "demo_job_batch": {
                "summary": "Demo job batch (scheduler/demo_job_batch.json)",
                "description": "16 jobs spanning carbon-only, cost-only, balanced, and priority-driven "
                                "weight combinations, for demoing carbon-aware placement across the horizon.",
                "value": _demo_batch_example,
            }
        },
    ),
):
    """Submit multiple jobs in one call. Inserts are atomic (all-or-nothing) and
    trigger a single re-solve for the whole batch, rather than one per job."""
    if not reqs:
        raise HTTPException(400, "request body must be a non-empty list of jobs")
    for req in reqs:
        _validate_job(req)

    conn = new_conn()
    try:
        with conn.cursor() as cur:
            results = [_insert_job(cur, req) for req in reqs]
        conn.commit()
    finally:
        conn.close()

    _trigger.set()
    return results


@app.get("/api/jobs")
def list_jobs():
    conn = new_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, label, job_type, duration_slots, priority, carbon_weight, cost_weight,
                       submitted_at, window_start, window_end, status
                FROM job_submissions ORDER BY submitted_at DESC LIMIT 100
            """)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


VALID_JOB_STATUSES = ("pending", "scheduled", "confirmed", "completed", "cancelled")


@app.delete("/api/jobs")
def clear_jobs(status: Optional[str] = None):
    """Clear job submissions (and their scheduled placements, if any) -- for
    resetting the demo queue. With no `status` query param, clears everything."""
    if status is not None and status not in VALID_JOB_STATUSES:
        raise HTTPException(400, f"status must be one of {VALID_JOB_STATUSES}")

    conn = new_conn()
    try:
        with conn.cursor() as cur:
            if status is None:
                cur.execute("DELETE FROM scheduled_jobs")
                cur.execute("DELETE FROM job_submissions")
            else:
                cur.execute("""
                    DELETE FROM scheduled_jobs
                    WHERE job_submission_id IN (SELECT id FROM job_submissions WHERE status = %s)
                """, (status,))
                cur.execute("DELETE FROM job_submissions WHERE status = %s", (status,))
            deleted = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    return {"deleted": deleted}


@app.get("/api/schedule")
def get_schedule():
    conn = new_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT sj.job_submission_id AS id, js.label, js.job_type, sj.data_centre_name,
                       sj.start_time, sj.end_time, sj.duration_slots,
                       sj.carbon_total_g, sj.cost_total_p, sj.status, sj.scheduled_at
                FROM scheduled_jobs sj
                JOIN job_submissions js ON js.id = sj.job_submission_id
                ORDER BY sj.start_time
            """)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@app.get("/api/grid")
def get_grid():
    conn = new_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT ts, data_centre, carbon_intensity_g_per_kwh, electricity_price_p
                FROM grid_forecasts
                WHERE ts >= NOW() - INTERVAL '30 minutes'
                ORDER BY ts, data_centre
            """)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Two demo-batch jobs get a schedulable window in the Swagger example, expressed
# as hours-from-now rather than a fixed date so the example stays usable no
# matter when /docs happens to be opened. app.openapi is left uncached (no
# assignment to app.openapi_schema) so this recomputes on every /openapi.json
# fetch -- i.e. every time the docs page is loaded, not just once at startup.
_EXAMPLE_WINDOWS_HOURS_FROM_NOW = {
    "Urgent CPU job — must start ASAP": (0, 1),
    "Overnight CPU batch — carbon-lean": (8, 16),
    "Overnight GPU batch — cost-lean": (10, 18),
}


def custom_openapi():
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    try:
        examples = schema["paths"]["/api/jobs/batch"]["post"]["requestBody"]["content"] \
            ["application/json"]["examples"]
        example = copy.deepcopy(examples["demo_job_batch"]["value"])
    except KeyError:
        return schema

    now = datetime.now(timezone.utc)
    for job in example:
        offsets = _EXAMPLE_WINDOWS_HOURS_FROM_NOW.get(job.get("label"))
        if offsets:
            start_h, end_h = offsets
            job["window_start"] = (now + timedelta(hours=start_h)).isoformat()
            job["window_end"] = (now + timedelta(hours=end_h)).isoformat()
    examples["demo_job_batch"]["value"] = example
    return schema


app.openapi = custom_openapi