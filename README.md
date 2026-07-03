# Architecture — iDT4GDC Grafana Operations Demo

**Version:** Demo Build  
**Stack:** Grafana 11 · PostgreSQL 16 · Python 3.12 · Docker Compose

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Repository Structure](#2-repository-structure)
3. [Runtime Topology](#3-runtime-topology)
4. [Telemetry Lifecycle](#4-telemetry-lifecycle)
5. [Persistence Model](#5-persistence-model)
6. [Dashboard Architecture](#6-dashboard-architecture)
7. [Filtering and Drill-Down Model](#7-filtering-and-drill-down-model)
8. [Alerting and Carbon Logic](#8-alerting-and-carbon-logic)
9. [Solar PV Forecaster](#9-solar-pv-forecaster)
10. [Carbon-Aware Scheduler](#10-carbon-aware-scheduler)
11. [Deployment and Local Run](#11-deployment-and-local-run)
12. [Operational Notes](#12-operational-notes)
13. [Design Decisions and Trade-offs](#13-design-decisions-and-trade-offs)
14. [Future Extensions](#14-future-extensions)

---

## 1. System Overview

This repository delivers a **Grafana-first operations dashboard demo** for iDT4GDC.  
It is designed to feel closer to a real control-room deployment than a custom application shell:

- Grafana provides the dashboard, filtering, refresh, and panel framework
- PostgreSQL acts as the telemetry store and query backend
- A Python simulator generates pseudo-live room / rack / server telemetry
- A Python forecaster runs a pre-trained TFT model to produce solar PV generation forecasts
- A Python scheduler assigns compute jobs to data centres using a carbon-aware CP-SAT solver
- Provisioned dashboards expose:
  - Connect Data Centre
  - Overview
  - Analytics
  - Carbon
  - Sustainability KPIs
  - AI Optimisation
  - GPU-FPGA Acceleration
  - Forecasting
  - Scheduler

The platform is intentionally demo-oriented:

- topology is realistic but synthetic
- telemetry is simulated, not production data
- refresh cadence is accelerated for presentations
- threshold logic is simple and explainable

---

## 2. Repository Structure

```text
idt4gdc-grafana-demo/
├── docker-compose.yml
├── README.md
│
├── postgres/
│   └── init/
│       └── 001-schema.sql
│
├── simulator/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   └── data/
│       ├── ai_model_results.json
│       ├── data_centres.json
│       ├── gpu_fpga_acceleration.json
│       └── sustainability_kpis.json
│
├── forecaster/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   └── forecast-data/          ← mounted read-only into the container
│       ├── metadata.csv        ← panel registry (ss_id, kWp, lat, lon)
│       ├── models/
│       │   └── forecast_global.pt
│       ├── data/
│       │   └── {ss_id}/
│       │       └── all.parquet ← half-hourly generation + weather covariates
│       └── scalers/
│           └── covariates/
│               └── global_{param}.pkl
│
├── scheduler/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py                  ← FastAPI service + scheduler loop
│   ├── model.py                ← CP-SAT solver (OR-Tools)
│   └── data/
│       ├── carbon_intensity.py ← NESO carbon intensity API client
│       └── energy_prices.py    ← Octopus Agile tariff API client
│
├── grafana/
│   ├── dashboards/
│   │   ├── connect_data_centre.json
│   │   ├── overview.json
│   │   ├── analytics.json
│   │   ├── carbon.json
│   │   ├── sustainability_kpis.json
│   │   ├── ai_optimisation.json
│   │   ├── gpu_fpga_acceleration.json
│   │   ├── forecasting.json
│   │   └── scheduler.json
│   └── provisioning/
│       ├── datasources/
│       │   └── postgres.yml
│       └── dashboards/
│           └── dashboards.yml
│
└── scripts/
    └── generate_dashboards.py
```

### Responsibility split

- `postgres/init/001-schema.sql`
  - schema, indexes, views, alert views
- `simulator/app.py`
  - dimensions, asset topology, pseudo-live telemetry generation
  - KPI snapshot generation
  - AI and acceleration demo seeding
- `simulator/data/*`
  - sample data-centre profiles
  - AI model benchmark data
  - sustainability KPI definitions
  - GPU / FPGA optimisation story data
- `forecaster/app.py`
  - loads the pre-trained TFT model and panel data at startup
  - backfills 7 days of solar PV forecasts into `forecast_generation`
  - runs the model daily at midnight UTC thereafter
- `forecaster/forecast-data/*`
  - user-provided model weights, panel metadata, historical parquet files, and fitted scalers
- `scheduler/app.py`
  - FastAPI job submission API
  - background scheduler loop (runs every 30 min)
  - fetches live carbon intensity and electricity prices from public APIs
  - stores grid forecasts in `grid_forecasts`
  - triggers the CP-SAT solver and writes results to `scheduled_jobs`
- `scheduler/model.py`
  - OR-Tools CP-SAT formulation: assigns jobs to data centres and time slots
- `scheduler/data/*`
  - thin API clients for NESO carbon intensity and Octopus Agile tariff data
- `scripts/generate_dashboards.py`
  - Grafana dashboard JSON generation
  - left-side demo navigation
  - fake connection flow wiring
- `grafana/provisioning/*`
  - datasource and dashboard bootstrapping

---

## 3. Runtime Topology

```mermaid
flowchart LR
    U["User / Browser"] --> G["Grafana :3000"]
    G --> P["PostgreSQL :5432 (host:5434)"]
    S["Simulator"] --> P
    F["Forecaster"] --> P
    SC["Scheduler :8000"] --> P
    SC --> NESO["NESO Carbon API"]
    SC --> OCT["Octopus Agile API"]

    subgraph DemoStack["Docker Compose Stack"]
        G
        P
        S
        F
        SC
    end
```

### Container roles

- **PostgreSQL**
  - stores topology, telemetry, forecast data, grid data, and scheduled jobs
- **Simulator**
  - seeds dimensions
  - backfills history
  - inserts live telemetry snapshots every 10 seconds
  - derives sustainability KPI snapshots from telemetry
  - seeds AI model comparison and GPU/FPGA optimisation scenario data
- **Forecaster**
  - loads a pre-trained TFT model and panel data at startup
  - backfills 7 days of solar PV generation forecasts
  - runs the model once daily at midnight UTC
  - writes results to `forecast_generation`
- **Scheduler**
  - exposes a FastAPI job submission API on port 8000
  - fetches carbon intensity (NESO) and electricity prices (Octopus Agile) every 30 minutes
  - runs a CP-SAT solver to assign jobs to data centres and time slots
  - writes results to `grid_forecasts` and `scheduled_jobs`
- **Grafana**
  - serves dashboards
  - queries PostgreSQL directly
  - applies data-centre and room / rack / server filters
  - acts as the demo shell through provisioned dashboard navigation

### Compose configuration

Notable runtime settings:

- PostgreSQL database: `opsdemo`
- Simulator history seed: `24` hours
- Historical step size: `300` seconds
- Live refresh interval: `10` seconds
- Grafana plugin install: `briangann-gauge-panel`
- Scheduler confirmation window: `2` slots (1 hour ahead)
- Forecaster backfill: `7` days
- Forecaster daily run hour: `0` UTC

---

## 4. Telemetry Lifecycle

The demo behaves like a small monitoring platform with synthetic but structured telemetry.

### Lifecycle summary

```mermaid
sequenceDiagram
    participant Boot as Docker Compose
    participant PG as PostgreSQL
    participant Sim as Simulator
    participant Grafana as Grafana
    participant User as User

    Boot->>PG: Start database
    Boot->>Sim: Start simulator
    Sim->>PG: Seed rooms / racks / assets
    Sim->>PG: Backfill 24h telemetry history
    Boot->>Grafana: Start Grafana
    Grafana->>PG: Load datasource and dashboards
    loop Every 10 seconds
        Sim->>PG: Insert latest telemetry snapshot
    end
    User->>Grafana: Open dashboard
    Grafana->>PG: Execute SQL queries on current filters
    PG-->>Grafana: Metrics, trends, alerts, carbon
```

### Telemetry generation model

Each asset snapshot calculates:

- `cpu_usage`
- `power_w`
- `inlet_temp_c`
- `outlet_temp_c`
- `emission_factor_kg_per_kwh`
- `carbon_kg`
- `status_level`
- `operational_state`

The simulator uses:

- business-cycle sine waves
- rack and room phase offsets
- GPU burst patterns
- storage-node lower-load behavior
- maintenance / standby windows for selected assets
- small random noise to avoid flat dashboard shapes

This creates dashboards that look live, variable, and operationally plausible without requiring external systems.

---

## 5. Persistence Model

### Core telemetry tables

#### `rooms`
- logical facility zones

#### `racks`
- belongs to a room
- includes:
  - `capacity_u`
  - `power_capacity_w`

#### `assets`
- room / rack / server inventory
- includes:
  - asset type
  - U position
  - U height
  - accessibility
  - nominal power

#### `telemetry_metrics`
- time-series fact table
- primary key: `(ts, asset_id)`

### Forecast table

#### `forecast_generation`
- primary key: `(ts, ss_id)`
- `ss_id` — solar panel system identifier
- `forecast_wh` — model-predicted generation in Wh (not null)
- `actual_wh` — recorded actual generation in Wh (null for future slots)
- `cloud_cover`, `shortwave_radiation` — stored alongside forecasts for dashboard use
- populated by the Forecaster service via upsert

### Scheduler tables

#### `grid_forecasts`
- primary key: `(ts, data_centre)`
- `carbon_intensity_g_per_kwh` — fetched from NESO API
- `electricity_price_p` — fetched from Octopus Agile API
- covers a 48-slot (24 h) rolling horizon, refreshed every 30 minutes

#### `job_submissions`
- primary key: `id` (serial)
- `job_type` — `CPU` or `GPU`
- `duration_slots` — number of 30-minute slots required
- `resource_count` — number of CPUs or GPUs needed
- `priority`, `carbon_weight`, `cost_weight` — solver objective inputs
- `window_start`, `window_end` — optional scheduling constraints
- `status` — `pending` → `scheduled` → `confirmed` → `completed`

#### `scheduled_jobs`
- primary key: `job_submission_id` (one row per job)
- links back to `job_submissions`
- `data_centre_name` — assigned data centre
- `start_slot`, `start_time`, `end_time` — scheduled placement
- `carbon_total_g`, `cost_total_p` — estimated cost of placement
- `status` — `scheduled`, `confirmed`, or `completed`

### Derived views

#### `latest_asset_metrics`
- most recent record per asset

#### `latest_rack_metrics`
- aggregated current rack state

#### `latest_room_metrics`
- aggregated current room state

#### `latest_site_summary`
- site-wide current status

#### `active_alerts`
- view-backed rule output for live dashboard alerts

#### `sustainability_kpi_snapshots`
- historical KPI series derived from simulated operational telemetry

#### `ai_model_results`
- model comparison metadata for the AI energy optimisation story

#### `data_centre_sources`
- fake but structured site connection profiles used by the Connect page

#### `gpu_fpga_*`
- hardware acceleration scenario tables for the fraud-detection story

### Why views are important

The dashboards intentionally query views for current-state panels so that:

- Grafana queries stay simpler
- current-state cards remain fast
- alert and summary logic is centralized in SQL

---

## 6. Dashboard Architecture

Dashboard generation is implemented in `scripts/generate_dashboards.py`.

The generator produces nine provisioned dashboards:

- `connect_data_centre.json`
- `overview.json`
- `analytics.json`
- `carbon.json`
- `sustainability_kpis.json`
- `ai_optimisation.json`
- `gpu_fpga_acceleration.json`
- `forecasting.json`
- `scheduler.json`

### Connect Data Centre dashboard

Focus:

- demo-friendly fake connection flow
- selectable data-centre profiles
- editable connection context fields
- handoff into operational dashboards
- left-side navigation across the whole demo

### Overview dashboard

Focus:

- current site status
- connected site context
- live KPI cards
- trend lines
- rack contribution
- active alerts
- live asset table

Panels include:

- stat cards
- animated needle gauges
- time-series charts
- bar gauges
- operational tables

### Analytics dashboard

Focus:

- forecasted draw
- anomaly pressure
- thermal peaks
- operational load patterns
- per-rack and per-asset analysis

### Carbon dashboard

Focus:

- live carbon pulse
- emission-factor visibility
- power-to-carbon relationship
- asset-level carbon hotspots
- sustainability-oriented operational view

### Sustainability KPIs dashboard

Focus:

- D3.2-aligned sustainability metrics
- current and historical KPI visibility
- gauge-based efficiency interpretation
- baseline versus current carbon comparison
- advanced KPI section for demo storytelling

### AI Optimisation dashboard

Focus:

- telemetry-driven power modelling story
- model comparison across LSTM / Random Forest / XGBoost families
- accuracy versus energy trade-off
- predicted versus actual power comparison
- feature importance and AI outcome summary

### GPU-FPGA Acceleration dashboard

Focus:

- workload orchestration story for fraud detection
- hardware platform comparison
- scenario controls and operational phases
- energy and latency improvement narrative

### Forecasting dashboard

Focus:

- 24-hour ahead solar PV generation forecast vs actuals
- cloud cover and shortwave radiation overlays
- per-panel forecast accuracy visibility

### Scheduler dashboard

Focus:

- 48-slot rolling grid forecast for each data centre (carbon intensity and electricity price)
- submitted job queue with status
- scheduled job placements across data centres
- carbon and cost totals per job

### Gauge implementation

The repo uses the **D3 Gauge plugin** for needle-style panels:

- plugin id: `briangann-gauge-panel`
- installed automatically through Compose
- configured with animated needle transitions

This gives the Grafana demo a more instrument-like, NOC-style presentation than the native gauge panel.

---

## 7. Filtering and Drill-Down Model

The dashboards are driven by a small set of Grafana variables:

- `data_centre`
- `site_location`
- `site_ip`
- `username`

- `room`
- `rack`
- `server`

Additional page-specific variables include:

- `ai_model`
- `scenario_phase`

These are generated in `scripts/generate_dashboards.py` and applied consistently across all dashboard SQL.

### Query behavior

- `room` filters available racks
- `rack` filters available servers
- `data_centre` carries the selected site context across dashboards
- all panel SQL applies the same filter logic
- `All` is handled through quoted raw Grafana variables to avoid SQL templating issues

### Why this matters

This repo deliberately supports:

- site-wide operations view
- fake site connection and context handoff
- room-level drill-down
- rack-level drill-down
- server-level isolation

without switching dashboards.

---

## 8. Alerting and Carbon Logic

### Alert rules

Alerts are expressed in SQL through the `active_alerts` view.

Current rules include:

- **CPU saturation**
  - critical at `cpu_usage >= 90`
- **Thermal envelope**
  - warning at `outlet_temp_c >= 34`
  - critical at `outlet_temp_c >= 36`
- **Power spike**
  - warning at `>= 1.08 × nominal power`
  - critical at `>= 1.18 × nominal power`
- **Operational state**
  - warning for `maintenance` and `standby`

### Carbon model

Carbon is estimated from instantaneous power:

```text
carbon_kg = (power_w / 1000) × emission_factor_kg_per_kwh
```

Emission factor itself is dynamic, not static:

- shaped by a daily renewable / balancing curve
- bounded to a realistic demo range
- visible in the Carbon dashboard

This keeps carbon behavior linked to operational load while still remaining easy to explain in a demo.

---

## 9. Solar PV Forecaster

The forecaster (`forecaster/app.py`) loads a pre-trained Temporal Fusion Transformer (TFT) model and produces 24-hour-ahead solar PV generation forecasts for one or more panel systems.

### Model and data

- **Model**: TFT trained with the Darts library, stored as `forecast-data/models/forecast_global.pt`
- **Resolution**: 30-minute intervals; 48-step (24 h) lookback and 48-step forecast horizon
- **Panel registry**: `forecast-data/metadata.csv` — one row per panel system with `ss_id`, `kWp`, `latitude_rounded`, `longitude_rounded`
- **Historical data**: `forecast-data/data/{ss_id}/all.parquet` — DatetimeIndex at 30-min frequency with columns:
  - `generation_Wh` — recorded solar generation
  - weather covariates: `cloud_cover`, `shortwave_radiation`, `direct_radiation`, `diffuse_radiation`, `temperature_2m`, `relative_humidity_2m`, `dew_point_2m`, `surface_pressure`, `wind_speed_10m`
- **Scalers**: one fitted sklearn scaler per covariate in `forecast-data/scalers/covariates/global_{param}.pkl`, applied before inference

Target generation is normalised to `generation_Wh / (kWp × 1000)` before model input and rescaled back after prediction.

### Time-shifting

The historical parquet data ends at a fixed past date. To make Grafana show current-looking timestamps, the forecaster computes an offset:

```text
time_offset = (today − 2 years + 1 day) − data_max_date
```

All timestamps stored in `forecast_generation` are shifted forward by this offset, so the data appears to cover the last seven days relative to today.

### Startup backfill and daily cadence

On startup the forecaster:

1. Loads the model and panel data into memory
2. Extends the dataframe by one day of zero-padded covariate rows (required for the model's future-covariate window)
3. Iterates over the last `BACKFILL_DAYS` (default 7) days and calls the model for each date
4. Upserts all rows into `forecast_generation` via `ON CONFLICT (ts, ss_id) DO UPDATE`

After backfill it sleeps until `RUN_HOUR` UTC (default midnight), then runs the model for the next day and repeats.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `BACKFILL_DAYS` | `7` | Days of history to populate on startup |
| `RUN_HOUR` | `0` | UTC hour for daily forecast run |
| `DATA_ROOT` | `/forecast-data` | Mount point for the data directory |
| `DATABASE_URL` | `postgresql://grafana:grafana@localhost:5432/opsdemo` | PostgreSQL connection string |

### Output table: `forecast_generation`

| Column | Type | Notes |
|---|---|---|
| `ts` | TIMESTAMPTZ | Forecast slot timestamp (time-shifted) |
| `ss_id` | INTEGER | Panel system identifier |
| `forecast_wh` | NUMERIC | Model-predicted generation in Wh |
| `actual_wh` | NUMERIC | Recorded actual (null for future slots) |
| `cloud_cover` | NUMERIC | Stored for dashboard overlay |
| `shortwave_radiation` | NUMERIC | Stored for dashboard overlay |

---

## 10. Carbon-Aware Scheduler

The scheduler (`scheduler/app.py`) is a FastAPI service with a background thread that runs every 30 minutes. It fetches live grid data, then uses a CP-SAT integer-programming solver to assign pending compute jobs to data centres and time slots that minimise carbon and cost.

### Grid data fetch policy

| Data | Source | Frequency |
|---|---|---|
| Carbon intensity (g CO₂/kWh) | NESO API (`carbonintensity.org.uk`) | Every 30-min run |
| Electricity price (p/kWh) | Octopus Agile API | Once daily, after 17:30 UTC |

On each 30-minute run the scheduler:

1. Fetches 24 h of carbon intensity forecasts per data centre (by postcode)
2. Fetches or reloads electricity prices for the same horizon
3. Stores the combined grid forecast in `grid_forecasts` (upsert)
4. Loads all pending and unconfirmed jobs from `job_submissions`
5. Runs the solver
6. Writes results to `scheduled_jobs`

If a new job is submitted via the API between scheduled runs, the background thread is woken immediately via a threading event and re-solves using cached grid data (no external API call).

### CP-SAT solver (`scheduler/model.py`)

The solver uses Google OR-Tools CP-SAT. Decision variables are binary: `x[dc][job][slot]` — whether job `j` starts at slot `i` in data centre `d`.

**Constraints:**

- Each job must start exactly once across all DCs and all slots
- Confirmed jobs are pinned to their existing DC and slot
- Optional `window_start` / `window_end` constraints exclude slots outside the job's allowed window
- Resource capacity: the total CPU (or GPU) demand of all overlapping jobs cannot exceed the DC's `available_cpus` / `available_gpus`

**Objective** (minimised):

```text
Σ jobs: (carbon_intensity_sum × carbon_weight) + (price_sum × cost_weight) + (start_slot × priority)
```

The `priority` term biases the solver toward earlier slots for higher-priority jobs when carbon and cost are similar.

**Data centres** (configurable via `DATA_CENTRES` env var):

| Name | Postcode | DNO Region | CPUs | GPUs |
|---|---|---|---|---|
| Reading | RG4 | J | 2048 | 256 |
| London | SW1A | C | 2048 | 256 |

### Confirmation lock

Jobs whose scheduled `start_slot` falls within the next `CONFIRMATION_SLOTS` (default 2) half-hour slots are set to `status='confirmed'`. Confirmed jobs are treated as pinned in subsequent solver runs and are not rescheduled unless they have already completed.

### Job lifecycle

```text
pending → scheduled → confirmed → completed
```

A job transitions from `scheduled` to `confirmed` when the scheduler run places it within the confirmation window. It transitions to `completed` when its `end_time` has passed.

### REST API

The scheduler exposes a REST API on port 8000:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/jobs` | Submit a new compute job |
| `GET` | `/api/jobs` | List all job submissions (last 100) |
| `GET` | `/api/schedule` | List all scheduled job placements |
| `GET` | `/api/grid` | Return current grid forecast data |
| `GET` | `/api/health` | Health check |

**Job submission fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `job_type` | string | `CPU` | `CPU` or `GPU` |
| `duration_slots` | integer | `4` | Number of 30-min slots required |
| `resource_count` | integer | `1` | CPUs or GPUs needed |
| `priority` | integer | `5` | Lower = more urgent |
| `carbon_weight` | float | `1.0` | Weight applied to carbon cost in objective |
| `cost_weight` | float | `1.0` | Weight applied to electricity cost in objective |
| `window_start` | datetime | null | Earliest allowed start time |
| `window_end` | datetime | null | Latest allowed start time |

### Output tables

**`grid_forecasts`** — rolling 48-slot grid state per data centre, refreshed each run.

**`scheduled_jobs`** — one row per job with assigned DC, slot, start/end times, and estimated carbon and cost totals.

---

## 11. Deployment and Local Run

### Start the demo

```bash
python scripts/generate_dashboards.py
docker compose up -d --build
```

### Access

- Grafana: [http://localhost:3000](http://localhost:3000)
- Username: `admin`
- Password: `admin`
- PostgreSQL: `localhost:5434`
- Scheduler API: [http://localhost:8000](http://localhost:8000)

Recommended entry point:

- [http://localhost:3000/d/idt4-connect/connect-data-centre?refresh=10s](http://localhost:3000/d/idt4-connect/connect-data-centre?refresh=10s)

### Stop the stack

```bash
docker compose down
```

### Rebuild after dashboard changes

```bash
python scripts/generate_dashboards.py
docker compose up -d --build
```

If dashboard JSON changes are not visible immediately, do a hard refresh in the browser.

---

## 12. Operational Notes

### Initial state

On a fresh run:

- dimensions are seeded
- the simulator backfills the last 24 hours
- the forecaster backfills 7 days of solar PV forecasts
- the scheduler fetches grid data and solves any queued jobs
- Grafana provisions dashboards automatically
- the default home dashboard is the Connect Data Centre page

### Refresh behavior

- live telemetry inserts every `10` seconds
- Grafana dashboards auto-refresh every `10` seconds
- scheduler grid data refreshes every `30` minutes
- forecaster runs once daily at midnight UTC

### Data characteristics

This repo contains **simulated demo telemetry**, not real production telemetry.

That is intentional because the objective is:

- local reproducibility
- easy demos
- controllable operational patterns
- no dependency on external DCIM or telemetry systems
- fake connection flow is UI-driven rather than truly stateful authentication

The forecaster does use real historical generation and weather data files supplied by the user, but timestamps are shifted to appear current.

The scheduler fetches real carbon intensity and electricity price data from public APIs (NESO and Octopus Agile). An internet connection is required for the scheduler to populate grid data.

---

## 13. Design Decisions and Trade-offs

### Why Grafana

Grafana was chosen for this demo because it gives:

- credible operations-dashboard UX
- native auto-refresh
- mature dashboard interactions
- easy filtering and drilling
- fast time-to-demo
- enough flexibility to simulate a product journey without building a full custom frontend

### Why PostgreSQL instead of a TSDB

PostgreSQL is sufficient here because:

- dataset size is small
- queries are explainable
- schema is easy to inspect
- setup is simpler for local reviewers

### Why a simulator instead of static CSV

Pseudo-live simulation is preferred because it:

- makes dashboards feel active
- keeps alert counts moving
- lets gauges and trends change naturally
- better resembles a monitoring environment

### Why CP-SAT for scheduling

OR-Tools CP-SAT gives:

- exact optimal or near-optimal solutions for small job counts
- native support for resource capacity constraints
- pinning of confirmed jobs without re-formulation
- deterministic, explainable assignment decisions

### Why time-shift the forecast data

The TFT model was trained on historical data ending at a fixed past date. Rather than retrain or fake inputs, a constant offset is applied at write time so that all stored timestamps appear current to Grafana without any runtime transformation in SQL.

### Known limitations

- no external authentication integration
- no real DCIM or BMS connection
- no persisted Grafana user state between clean recreations
- no custom rack-layout Digital Twin screen inside Grafana
- the connection flow is simulated through dashboard variables and links, not a true backend session
- the forecaster runs a single panel system per container instance (`SS_ID`)
- the scheduler requires internet access to fetch live grid data; it falls back to defaults (`200 g/kWh`, `15 p/kWh`) if API calls fail

---

## 14. Future Extensions

The next realistic upgrade paths are:

1. Replace simulator input with a real ingestion adapter
   - Prometheus
   - Kafka
   - MQTT
   - DCIM export

2. Add a rack-layout / floor-layout dashboard
   - Canvas panel
   - SVG panel
   - external plugin-based topology panel

3. Expand carbon analytics
   - per-room sustainability KPIs
   - renewable share overlays
   - trend comparison windows

4. Introduce role-based access and multiple demo personas

5. Add incident workflows
   - acknowledgement
   - maintenance windows
   - recovery tracking

---

## Summary

This repository is best understood as a **self-contained, pseudo-live operations dashboard demo** for iDT4GDC:

- PostgreSQL provides the operational data model
- the simulator provides realistic changing telemetry
- the forecaster provides 24-hour-ahead solar PV generation forecasts using a pre-trained TFT model
- the scheduler provides carbon-aware compute job placement using CP-SAT optimisation against live grid data
- Grafana provides the monitoring experience
- dashboards provide current-state, analytic, carbon, forecasting, and scheduling visibility
- AI and sustainability modules extend the story from monitoring into optimisation and KPI interpretation

It is intentionally simple to run, easy to explain, and strong enough for stakeholder review, internal demos, and architecture discussions.