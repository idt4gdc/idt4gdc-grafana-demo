CREATE TABLE IF NOT EXISTS rooms (
    room_id TEXT PRIMARY KEY,
    room_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS racks (
    rack_id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL REFERENCES rooms(room_id),
    rack_name TEXT NOT NULL,
    capacity_u INTEGER NOT NULL,
    power_capacity_w NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    asset_name TEXT NOT NULL,
    room_id TEXT NOT NULL REFERENCES rooms(room_id),
    room_name TEXT NOT NULL,
    rack_id TEXT NOT NULL REFERENCES racks(rack_id),
    rack_name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    u_position INTEGER NOT NULL,
    u_height INTEGER NOT NULL,
    accessible BOOLEAN NOT NULL DEFAULT TRUE,
    nominal_power_w NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_metrics (
    ts TIMESTAMPTZ NOT NULL,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    cpu_usage NUMERIC NOT NULL,
    power_w NUMERIC NOT NULL,
    inlet_temp_c NUMERIC NOT NULL,
    outlet_temp_c NUMERIC NOT NULL,
    emission_factor_kg_per_kwh NUMERIC NOT NULL,
    carbon_kg NUMERIC NOT NULL,
    status_level TEXT NOT NULL,
    operational_state TEXT NOT NULL,
    PRIMARY KEY (ts, asset_id)
);

CREATE TABLE IF NOT EXISTS ai_model_results (
    model_name TEXT PRIMARY KEY,
    model_type TEXT NOT NULL,
    purpose TEXT NOT NULL,
    energy_j NUMERIC,
    accuracy_percent NUMERIC,
    interpretation TEXT NOT NULL,
    best_model BOOLEAN NOT NULL DEFAULT FALSE,
    preferred_family BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS ai_model_features (
    feature_name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_feature_importance (
    model_name TEXT NOT NULL REFERENCES ai_model_results(model_name),
    feature_name TEXT NOT NULL REFERENCES ai_model_features(feature_name),
    importance_score NUMERIC NOT NULL,
    PRIMARY KEY (model_name, feature_name)
);

CREATE TABLE IF NOT EXISTS sustainability_kpi_config (
    profile_name TEXT PRIMARY KEY,
    facility_overhead_base NUMERIC NOT NULL,
    facility_overhead_wave NUMERIC NOT NULL,
    renewable_fraction_base NUMERIC NOT NULL,
    renewable_fraction_wave NUMERIC NOT NULL,
    reused_energy_fraction_base NUMERIC NOT NULL,
    reused_energy_fraction_wave NUMERIC NOT NULL,
    baseline_co2_multiplier NUMERIC NOT NULL,
    performance_factor NUMERIC NOT NULL,
    cue_it_energy_share NUMERIC NOT NULL,
    hue_base NUMERIC NOT NULL,
    she_base NUMERIC NOT NULL,
    apcren_base NUMERIC NOT NULL,
    dca_base NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS sustainability_kpi_metadata (
    kpi_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    direction TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    is_advanced BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sustainability_kpi_snapshots (
    ts TIMESTAMPTZ PRIMARY KEY,
    total_facility_power_w NUMERIC NOT NULL,
    it_power_w NUMERIC NOT NULL,
    total_energy_kwh NUMERIC NOT NULL,
    renewable_energy_kwh NUMERIC NOT NULL,
    reused_energy_kwh NUMERIC NOT NULL,
    total_co2_kg NUMERIC NOT NULL,
    baseline_co2_kg NUMERIC NOT NULL,
    performance_score NUMERIC NOT NULL,
    it_energy_kwh NUMERIC NOT NULL,
    pue NUMERIC NOT NULL,
    ref NUMERIC NOT NULL,
    erf NUMERIC NOT NULL,
    cef NUMERIC NOT NULL,
    co2_savings_kg NUMERIC NOT NULL,
    ppw NUMERIC NOT NULL,
    cue NUMERIC NOT NULL,
    hue NUMERIC NOT NULL,
    she NUMERIC NOT NULL,
    apcren NUMERIC NOT NULL,
    dca NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS data_centre_sources (
    dc_key TEXT PRIMARY KEY,
    dc_name TEXT NOT NULL,
    location TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    source_type TEXT NOT NULL,
    default_username TEXT NOT NULL,
    default_password TEXT NOT NULL,
    jwt_status TEXT NOT NULL,
    stream_status TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    user_visible BOOLEAN NOT NULL DEFAULT TRUE,
    user_added BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS gpu_fpga_workload (
    workload_name TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    goal TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gpu_fpga_platform_metrics (
    platform TEXT PRIMARY KEY,
    role_description TEXT NOT NULL,
    training_latency_ms NUMERIC NOT NULL,
    inference_latency_ms NUMERIC NOT NULL,
    speedup_training NUMERIC NOT NULL,
    speedup_inference NUMERIC NOT NULL,
    performance_per_watt NUMERIC NOT NULL,
    power_w NUMERIC NOT NULL,
    throughput NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS gpu_fpga_scenario (
    scenario_name TEXT PRIMARY KEY,
    baseline_platform TEXT NOT NULL,
    training_platform TEXT NOT NULL,
    inference_platform TEXT NOT NULL,
    baseline_energy_j NUMERIC NOT NULL,
    optimised_energy_j NUMERIC NOT NULL,
    baseline_co2_kg NUMERIC NOT NULL,
    optimised_co2_kg NUMERIC NOT NULL,
    energy_saving_percent NUMERIC NOT NULL,
    throughput_improvement_percent NUMERIC NOT NULL,
    fpga_inference_speedup NUMERIC NOT NULL,
    fpga_perf_per_watt NUMERIC NOT NULL,
    gpu_training_acceleration NUMERIC NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_asset_ts ON telemetry_metrics (asset_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry_metrics (ts DESC);
CREATE INDEX IF NOT EXISTS idx_sustainability_ts ON sustainability_kpi_snapshots (ts DESC);

CREATE OR REPLACE VIEW latest_asset_metrics AS
SELECT DISTINCT ON (tm.asset_id)
    tm.ts,
    tm.asset_id,
    tm.cpu_usage,
    tm.power_w,
    tm.inlet_temp_c,
    tm.outlet_temp_c,
    tm.emission_factor_kg_per_kwh,
    tm.carbon_kg,
    tm.status_level,
    tm.operational_state
FROM telemetry_metrics tm
ORDER BY tm.asset_id, tm.ts DESC;

CREATE OR REPLACE VIEW latest_rack_metrics AS
SELECT
    a.room_id,
    a.room_name,
    a.rack_id,
    a.rack_name,
    MAX(l.ts) AS ts,
    ROUND(AVG(l.cpu_usage)::NUMERIC, 2) AS avg_cpu_usage,
    ROUND(SUM(l.power_w)::NUMERIC, 2) AS rack_power_w,
    ROUND(AVG(l.inlet_temp_c)::NUMERIC, 2) AS avg_inlet_temp_c,
    ROUND(AVG(l.outlet_temp_c)::NUMERIC, 2) AS avg_outlet_temp_c,
    ROUND(SUM(l.carbon_kg)::NUMERIC, 4) AS rack_carbon_kg,
    COUNT(*) FILTER (WHERE l.status_level = 'critical') AS critical_assets,
    COUNT(*) FILTER (WHERE l.status_level = 'warning') AS warning_assets
FROM latest_asset_metrics l
JOIN assets a USING (asset_id)
GROUP BY a.room_id, a.room_name, a.rack_id, a.rack_name;

CREATE OR REPLACE VIEW latest_room_metrics AS
SELECT
    a.room_id,
    a.room_name,
    MAX(l.ts) AS ts,
    ROUND(AVG(l.cpu_usage)::NUMERIC, 2) AS avg_cpu_usage,
    ROUND(SUM(l.power_w)::NUMERIC, 2) AS room_power_w,
    ROUND(AVG(l.inlet_temp_c)::NUMERIC, 2) AS avg_inlet_temp_c,
    ROUND(AVG(l.outlet_temp_c)::NUMERIC, 2) AS avg_outlet_temp_c,
    ROUND(SUM(l.carbon_kg)::NUMERIC, 4) AS room_carbon_kg,
    COUNT(*) FILTER (WHERE l.status_level = 'critical') AS critical_assets,
    COUNT(*) FILTER (WHERE l.status_level = 'warning') AS warning_assets
FROM latest_asset_metrics l
JOIN assets a USING (asset_id)
GROUP BY a.room_id, a.room_name;

CREATE OR REPLACE VIEW latest_site_summary AS
SELECT
    MAX(l.ts) AS ts,
    ROUND(SUM(l.power_w)::NUMERIC, 2) AS current_power_w,
    ROUND(AVG(l.cpu_usage)::NUMERIC, 2) AS avg_cpu_usage,
    ROUND(AVG(l.inlet_temp_c)::NUMERIC, 2) AS avg_inlet_temp_c,
    ROUND(SUM(l.carbon_kg)::NUMERIC, 4) AS current_carbon_kg,
    COUNT(*) FILTER (WHERE l.status_level = 'critical') AS critical_assets,
    COUNT(*) FILTER (WHERE l.status_level = 'warning') AS warning_assets
FROM latest_asset_metrics l;

CREATE OR REPLACE VIEW latest_sustainability_snapshot AS
SELECT s.*
FROM sustainability_kpi_snapshots s
ORDER BY s.ts DESC
LIMIT 1;

CREATE OR REPLACE VIEW sustainability_prom_metrics AS
SELECT ts, 'idt4gdc_pue'::TEXT AS metric_name, pue AS metric_value FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_ref'::TEXT, ref FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_erf'::TEXT, erf FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_cue'::TEXT, cue FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_cef_kgco2_per_kwh'::TEXT, cef FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_co2_savings_kg'::TEXT, co2_savings_kg FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_ppw'::TEXT, ppw FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_hue'::TEXT, hue FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_she'::TEXT, she FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_apcren'::TEXT, apcren FROM latest_sustainability_snapshot
UNION ALL
SELECT ts, 'idt4gdc_dca'::TEXT, dca FROM latest_sustainability_snapshot;

CREATE OR REPLACE VIEW latest_connection_status AS
SELECT
    d.dc_key,
    d.dc_name,
    d.location,
    d.ip_address,
    d.source_type,
    d.default_username,
    d.default_password,
    d.jwt_status,
    d.stream_status,
    s.ts AS last_sync
FROM data_centre_sources d
CROSS JOIN latest_site_summary s;

CREATE OR REPLACE VIEW gpu_fpga_prom_metrics AS
SELECT platform, 'idt4gdc_fraud_training_latency_ms'::TEXT AS metric_name, training_latency_ms AS metric_value
FROM gpu_fpga_platform_metrics
UNION ALL
SELECT platform, 'idt4gdc_fraud_inference_latency_ms'::TEXT, inference_latency_ms
FROM gpu_fpga_platform_metrics
UNION ALL
SELECT platform, 'idt4gdc_fraud_speedup_training'::TEXT, speedup_training
FROM gpu_fpga_platform_metrics
UNION ALL
SELECT platform, 'idt4gdc_fraud_speedup_inference'::TEXT, speedup_inference
FROM gpu_fpga_platform_metrics
UNION ALL
SELECT platform, 'idt4gdc_fraud_perf_per_watt'::TEXT, performance_per_watt
FROM gpu_fpga_platform_metrics
UNION ALL
SELECT baseline_platform AS platform, 'idt4gdc_optimization_improvement_percent'::TEXT, energy_saving_percent
FROM gpu_fpga_scenario
UNION ALL
SELECT training_platform AS platform, 'idt4gdc_ai_scheduler_state'::TEXT, 1::NUMERIC
FROM gpu_fpga_scenario;

CREATE OR REPLACE VIEW active_alerts AS
SELECT
    l.ts,
    a.room_id,
    a.room_name,
    a.rack_id,
    a.rack_name,
    a.asset_id,
    a.asset_name,
    'critical'::TEXT AS severity,
    'CPU saturation'::TEXT AS rule_name,
    FORMAT('%s CPU at %s%%', a.asset_name, ROUND(l.cpu_usage, 1)) AS message,
    ROUND(l.cpu_usage, 1) AS metric_value,
    90::NUMERIC AS threshold
FROM latest_asset_metrics l
JOIN assets a USING (asset_id)
WHERE l.cpu_usage >= 90

UNION ALL

SELECT
    l.ts,
    a.room_id,
    a.room_name,
    a.rack_id,
    a.rack_name,
    a.asset_id,
    a.asset_name,
    CASE WHEN l.outlet_temp_c >= 36 THEN 'critical' ELSE 'warning' END AS severity,
    'Thermal envelope'::TEXT AS rule_name,
    FORMAT('%s outlet temp at %s C', a.asset_name, ROUND(l.outlet_temp_c, 1)) AS message,
    ROUND(l.outlet_temp_c, 1) AS metric_value,
    34::NUMERIC AS threshold
FROM latest_asset_metrics l
JOIN assets a USING (asset_id)
WHERE l.outlet_temp_c >= 34

UNION ALL

SELECT
    l.ts,
    a.room_id,
    a.room_name,
    a.rack_id,
    a.rack_name,
    a.asset_id,
    a.asset_name,
    CASE WHEN l.power_w >= a.nominal_power_w * 1.18 THEN 'critical' ELSE 'warning' END AS severity,
    'Power spike'::TEXT AS rule_name,
    FORMAT('%s draw at %s W', a.asset_name, ROUND(l.power_w, 0)) AS message,
    ROUND(l.power_w, 0) AS metric_value,
    ROUND(a.nominal_power_w * 1.08, 0) AS threshold
FROM latest_asset_metrics l
JOIN assets a USING (asset_id)
WHERE l.power_w >= a.nominal_power_w * 1.08

UNION ALL

SELECT
    l.ts,
    a.room_id,
    a.room_name,
    a.rack_id,
    a.rack_name,
    a.asset_id,
    a.asset_name,
    'warning'::TEXT AS severity,
    'Operational state'::TEXT AS rule_name,
    FORMAT('%s currently in %s state', a.asset_name, l.operational_state) AS message,
    1::NUMERIC AS metric_value,
    0::NUMERIC AS threshold
FROM latest_asset_metrics l
JOIN assets a USING (asset_id)
WHERE l.operational_state IN ('maintenance', 'standby');
