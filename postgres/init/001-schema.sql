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

CREATE INDEX IF NOT EXISTS idx_telemetry_asset_ts ON telemetry_metrics (asset_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry_metrics (ts DESC);

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

