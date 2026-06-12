import json
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "grafana" / "dashboards"
DATASOURCE = {"type": "postgres", "uid": "postgres-ops"}
PLUGIN_VERSION = "11.0.0"
ROOM_VAR = "${room:raw}"
RACK_VAR = "${rack:raw}"
SERVER_VAR = "${server:raw}"
FILTERS = dedent(
    f"""
    ({ROOM_VAR} = 'All' OR a.room_name = {ROOM_VAR})
    AND ({RACK_VAR} = 'All' OR a.rack_name = {RACK_VAR})
    AND ({SERVER_VAR} = 'All' OR a.asset_name = {SERVER_VAR})
    """
).strip()


class PanelIds:
    def __init__(self):
        self.current = 0

    def next(self):
        self.current += 1
        return self.current


def room_variable():
    query = "SELECT room_name AS __text, quote_literal(room_name) AS __value FROM rooms ORDER BY room_name"
    return {
        "name": "room",
        "label": "Room",
        "type": "query",
        "datasource": DATASOURCE,
        "definition": query,
        "query": query,
        "includeAll": True,
        "allValue": "'All'",
        "multi": False,
        "refresh": 2,
        "sort": 1,
        "current": {"selected": True, "text": "All", "value": "'All'"},
    }


def rack_variable():
    query = dedent(
        f"""
        SELECT rack_name AS __text, quote_literal(rack_name) AS __value
        FROM racks
        JOIN rooms USING (room_id)
        WHERE {ROOM_VAR} = 'All' OR rooms.room_name = {ROOM_VAR}
        ORDER BY rack_name
        """
    ).strip()
    return {
        "name": "rack",
        "label": "Rack",
        "type": "query",
        "datasource": DATASOURCE,
        "definition": query,
        "query": query,
        "includeAll": True,
        "allValue": "'All'",
        "multi": False,
        "refresh": 2,
        "sort": 1,
        "current": {"selected": True, "text": "All", "value": "'All'"},
    }


def server_variable():
    query = dedent(
        f"""
        SELECT asset_name AS __text, quote_literal(asset_name) AS __value
        FROM assets
        WHERE ({ROOM_VAR} = 'All' OR room_name = {ROOM_VAR})
          AND ({RACK_VAR} = 'All' OR rack_name = {RACK_VAR})
        ORDER BY asset_name
        """
    ).strip()
    return {
        "name": "server",
        "label": "Server",
        "type": "query",
        "datasource": DATASOURCE,
        "definition": query,
        "query": query,
        "includeAll": True,
        "allValue": "'All'",
        "multi": False,
        "refresh": 2,
        "sort": 1,
        "current": {"selected": True, "text": "All", "value": "'All'"},
    }


def annotations():
    return {
        "list": [
            {
                "builtIn": 1,
                "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                "enable": True,
                "hide": True,
                "iconColor": "rgba(0, 211, 255, 1)",
                "name": "Annotations & Alerts",
                "type": "dashboard",
            }
        ]
    }


def dashboard_base(title, uid, panels, time_from="now-6h"):
    return {
        "annotations": annotations(),
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": panels,
        "refresh": "10s",
        "schemaVersion": 39,
        "style": "dark",
        "tags": ["idt4gdc", "demo", "ops"],
        "templating": {"list": [room_variable(), rack_variable(), server_variable()]},
        "time": {"from": time_from, "to": "now"},
        "timepicker": {},
        "timezone": "",
        "title": title,
        "uid": uid,
        "version": 1,
        "weekStart": "",
    }


def target(sql, ref_id="A", fmt="table"):
    return {
        "datasource": DATASOURCE,
        "format": fmt,
        "rawQuery": True,
        "rawSql": dedent(sql).strip(),
        "refId": ref_id,
    }


def stat_panel(panel_ids, title, sql, unit, x, y, w, h, thresholds=None):
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": thresholds or [{"color": "green", "value": None}],
                },
                "unit": unit,
            },
            "overrides": [],
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_ids.next(),
        "options": {
            "colorMode": "background",
            "graphMode": "none",
            "justifyMode": "center",
            "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "value_and_name",
        },
        "pluginVersion": PLUGIN_VERSION,
        "targets": [target(sql)],
        "title": title,
        "type": "stat",
    }


def timeseries_panel(panel_ids, title, sql, unit, x, y, w, h):
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {
                    "drawStyle": "line",
                    "fillOpacity": 12,
                    "lineInterpolation": "smooth",
                    "lineWidth": 2,
                    "showPoints": "never",
                    "spanNulls": True,
                },
                "mappings": [],
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
                "unit": unit,
            },
            "overrides": [],
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_ids.next(),
        "options": {
            "legend": {"displayMode": "table", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "none"},
        },
        "pluginVersion": PLUGIN_VERSION,
        "targets": [target(sql, fmt="time_series")],
        "title": title,
        "type": "timeseries",
    }


def table_panel(panel_ids, title, sql, x, y, w, h):
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {"defaults": {}, "overrides": []},
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_ids.next(),
        "options": {
            "cellHeight": "sm",
            "footer": {"show": False},
            "showHeader": True,
        },
        "pluginVersion": PLUGIN_VERSION,
        "targets": [target(sql)],
        "title": title,
        "type": "table",
    }


def bargauge_panel(panel_ids, title, sql, unit, x, y, w, h, thresholds=None):
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": thresholds
                    or [
                        {"color": "green", "value": None},
                        {"color": "yellow", "value": 2500},
                        {"color": "red", "value": 3200},
                    ],
                },
                "unit": unit,
            },
            "overrides": [],
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_ids.next(),
        "options": {
            "displayMode": "basic",
            "orientation": "horizontal",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showUnfilled": True,
        },
        "pluginVersion": PLUGIN_VERSION,
        "targets": [target(sql)],
        "title": title,
        "type": "bargauge",
    }


def gauge_tick_spacing(min_value, max_value):
    span = max_value - min_value
    if span <= 1:
        return 0.1, 0.05
    if span <= 15:
        return 2, 1
    if span <= 30:
        return 5, 1
    if span <= 60:
        return 10, 2
    if span <= 120:
        return 20, 5
    if span <= 300:
        return 50, 10
    if span <= 1000:
        return 100, 20
    if span <= 3000:
        return 500, 100
    if span <= 12000:
        return 2000, 500
    return max(span / 5, 1), max(span / 20, 1)


def gauge_panel(panel_ids, title, sql, unit, x, y, w, h, min_value, max_value, thresholds=None, decimals=None):
    major_tick, minor_tick = gauge_tick_spacing(min_value, max_value)
    defaults = {
        "color": {"mode": "fixed"},
        "mappings": [],
        "thresholds": {
            "mode": "absolute",
            "steps": thresholds or [{"color": "green", "value": None}],
        },
        "unit": unit,
        "custom": {"displayMode": "basic"},
    }
    if decimals is not None:
        defaults["decimals"] = decimals

    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": defaults,
            "overrides": [],
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_ids.next(),
        "options": {
            "operatorName": "lastNotNull",
            "minValue": min_value,
            "maxValue": max_value,
            "showValue": True,
            "showTitle": False,
            "showTickLabels": True,
            "formatTickLabelsWithUnit": False,
            "animateNeedleValueTransition": True,
            "animateNeedleValueTransitionSpeed": 900,
            "allowNeedleCrossLimits": False,
            "needleWidth": 6,
            "markerEndEnabled": True,
            "markerEndShape": "circle",
            "markerStartEnabled": False,
            "showThresholdBandOnGauge": True,
            "showThresholdBandLowerRange": True,
            "showThresholdBandMiddleRange": True,
            "showThresholdBandUpperRange": True,
            "showThresholdStateOnBackground": False,
            "showThresholdStateOnValue": True,
            "showThresholdStateOnTitle": False,
            "zeroTickAngle": 60,
            "maxTickAngle": 300,
            "zeroNeedleAngle": 40,
            "maxNeedleAngle": 320,
            "tickSpacingMajor": major_tick,
            "tickSpacingMinor": minor_tick,
            "gaugeRadius": 0,
            "padding": 0.05,
            "edgeWidth": 0.05,
            "pivotRadius": 0.1,
            "tickEdgeGap": 0.05,
            "tickLengthMaj": 0.15,
            "tickLengthMin": 0.05,
            "tickWidthMajor": 5,
            "tickWidthMinor": 1,
            "needleTickGap": 0.05,
            "needleLengthNeg": 0,
            "outerEdgeColor": "#3a4655",
            "innerColor": "#1f2430",
            "pivotColor": "#b8bfcc",
            "needleColor": "#f4f7fb",
            "tickLabelColor": "#c9d1dd",
            "tickMajorColor": "#7f8da3",
            "tickMinorColor": "#526174",
            "valueFont": "Roboto",
            "valueFontSize": "70",
            "tickFont": "Roboto",
            "tickLabelFontSize": "18",
            "titleFont": "Roboto",
            "titleFontSize": "20",
        },
        "pluginVersion": PLUGIN_VERSION,
        "targets": [target(sql)],
        "title": title,
        "type": "briangann-gauge-panel",
    }


def overview_dashboard():
    p = PanelIds()
    panels = [
        stat_panel(
            p,
            "Site Power Draw",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(SUM(l.power_w), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "watt",
            0,
            0,
            4,
            4,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 7000}, {"color": "red", "value": 9500}],
        ),
        stat_panel(
            p,
            "Average CPU",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(AVG(l.cpu_usage), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "percent",
            4,
            0,
            4,
            4,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 85}],
        ),
        stat_panel(
            p,
            "Average Inlet Temp",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(AVG(l.inlet_temp_c), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "celsius",
            8,
            0,
            4,
            4,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 24}, {"color": "red", "value": 27}],
        ),
        stat_panel(
            p,
            "Active Alerts",
            f"""
            SELECT NOW() AS time, COUNT(*)::NUMERIC AS value
            FROM active_alerts
            WHERE ({ROOM_VAR} = 'All' OR room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR rack_name = {RACK_VAR})
              AND ({SERVER_VAR} = 'All' OR asset_name = {SERVER_VAR})
            """,
            "none",
            12,
            0,
            4,
            4,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 5}],
        ),
        stat_panel(
            p,
            "Current CO2",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(SUM(l.carbon_kg), 0)::NUMERIC, 3) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "suffix:kg CO2e",
            16,
            0,
            4,
            4,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 0.22}, {"color": "red", "value": 0.35}],
        ),
        stat_panel(
            p,
            "Assets in Scope",
            f"""
            SELECT NOW() AS time, COUNT(*)::NUMERIC AS value
            FROM assets a
            WHERE {FILTERS}
            """,
            "none",
            20,
            0,
            4,
            4,
        ),
        gauge_panel(
            p,
            "Power Capacity",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(SUM(l.power_w), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "watt",
            0,
            4,
            6,
            7,
            0,
            11000,
            [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 7000},
                {"color": "red", "value": 9500},
            ],
            0,
        ),
        gauge_panel(
            p,
            "CPU Load",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(AVG(l.cpu_usage), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "percent",
            6,
            4,
            6,
            7,
            0,
            100,
            [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 70},
                {"color": "red", "value": 85},
            ],
            1,
        ),
        gauge_panel(
            p,
            "Inlet Thermal State",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(AVG(l.inlet_temp_c), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "celsius",
            12,
            4,
            6,
            7,
            18,
            30,
            [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 24},
                {"color": "red", "value": 27},
            ],
            1,
        ),
        gauge_panel(
            p,
            "Carbon Pulse",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(SUM(l.carbon_kg), 0)::NUMERIC, 3) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "suffix:kg CO2e",
            18,
            4,
            6,
            7,
            0,
            0.45,
            [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 0.22},
                {"color": "red", "value": 0.35},
            ],
            3,
        ),
        timeseries_panel(
            p,
            "Power Trend",
            f"""
            SELECT
              $__timeGroupAlias(tm.ts, '5m'),
              'Power Draw' AS metric,
              ROUND(SUM(tm.power_w)::NUMERIC, 1) AS value
            FROM telemetry_metrics tm
            JOIN assets a USING (asset_id)
            WHERE $__timeFilter(tm.ts) AND {FILTERS}
            GROUP BY 1
            ORDER BY 1
            """,
            "watt",
            0,
            11,
            12,
            8,
        ),
        timeseries_panel(
            p,
            "CPU Utilisation Trend",
            f"""
            SELECT
              $__timeGroupAlias(tm.ts, '5m'),
              'Average CPU' AS metric,
              ROUND(AVG(tm.cpu_usage)::NUMERIC, 1) AS value
            FROM telemetry_metrics tm
            JOIN assets a USING (asset_id)
            WHERE $__timeFilter(tm.ts) AND {FILTERS}
            GROUP BY 1
            ORDER BY 1
            """,
            "percent",
            12,
            11,
            12,
            8,
        ),
        timeseries_panel(
            p,
            "Thermal Envelope",
            f"""
            SELECT
              bucket AS time,
              metric,
              value
            FROM (
              SELECT
                $__timeGroup(tm.ts, '5m') AS bucket,
                'Inlet Temp' AS metric,
                ROUND(AVG(tm.inlet_temp_c)::NUMERIC, 1) AS value
              FROM telemetry_metrics tm
              JOIN assets a USING (asset_id)
              WHERE $__timeFilter(tm.ts) AND {FILTERS}
              GROUP BY 1
              UNION ALL
              SELECT
                $__timeGroup(tm.ts, '5m') AS bucket,
                'Outlet Temp' AS metric,
                ROUND(AVG(tm.outlet_temp_c)::NUMERIC, 1) AS value
              FROM telemetry_metrics tm
              JOIN assets a USING (asset_id)
              WHERE $__timeFilter(tm.ts) AND {FILTERS}
              GROUP BY 1
            ) s
            ORDER BY 1, 2
            """,
            "celsius",
            0,
            19,
            12,
            8,
        ),
        bargauge_panel(
            p,
            "Rack Power Contribution",
            f"""
            SELECT
              a.rack_name AS metric,
              ROUND(SUM(l.power_w)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE ({ROOM_VAR} = 'All' OR a.room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR a.rack_name = {RACK_VAR})
            GROUP BY a.rack_name
            ORDER BY value DESC
            """,
            "watt",
            12,
            19,
            12,
            8,
        ),
        table_panel(
            p,
            "Active Alert Feed",
            f"""
            SELECT
              ts AS "Last seen",
              room_name AS "Room",
              rack_name AS "Rack",
              asset_name AS "Asset",
              severity AS "Severity",
              rule_name AS "Rule",
              message AS "Message"
            FROM active_alerts
            WHERE ({ROOM_VAR} = 'All' OR room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR rack_name = {RACK_VAR})
              AND ({SERVER_VAR} = 'All' OR asset_name = {SERVER_VAR})
            ORDER BY ts DESC, severity DESC
            LIMIT 25
            """,
            0,
            27,
            12,
            8,
        ),
        table_panel(
            p,
            "Live Asset Status",
            f"""
            SELECT
              l.ts AS "Last update",
              a.room_name AS "Room",
              a.rack_name AS "Rack",
              a.asset_name AS "Server",
              a.asset_type AS "Type",
              ROUND(l.cpu_usage::NUMERIC, 1) AS "CPU %",
              ROUND(l.power_w::NUMERIC, 0) AS "Power W",
              ROUND(l.outlet_temp_c::NUMERIC, 1) AS "Outlet C",
              l.status_level AS "Status",
              l.operational_state AS "State"
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            ORDER BY
              CASE l.status_level
                WHEN 'critical' THEN 1
                WHEN 'warning' THEN 2
                ELSE 3
              END,
              l.cpu_usage DESC
            LIMIT 25
            """,
            12,
            27,
            12,
            8,
        ),
    ]
    return dashboard_base("iDT4GDC Overview", "idt4-overview", panels)


def analytics_dashboard():
    p = PanelIds()
    panels = [
        gauge_panel(
            p,
            "Current Draw",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(SUM(l.power_w), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "watt",
            0,
            0,
            6,
            7,
            0,
            11000,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 7000}, {"color": "red", "value": 9500}],
            0,
        ),
        gauge_panel(
            p,
            "15m Forecast",
            f"""
            WITH scoped AS (
              SELECT tm.ts, tm.power_w
              FROM telemetry_metrics tm
              JOIN assets a USING (asset_id)
              WHERE tm.ts >= NOW() - INTERVAL '30 minutes'
                AND {FILTERS}
            ),
            windows AS (
              SELECT
                AVG(power_w) FILTER (WHERE ts >= NOW() - INTERVAL '15 minutes') AS current_avg,
                AVG(power_w) FILTER (
                  WHERE ts >= NOW() - INTERVAL '30 minutes'
                    AND ts < NOW() - INTERVAL '15 minutes'
                ) AS previous_avg
              FROM scoped
            )
            SELECT
              NOW() AS time,
              ROUND(COALESCE(current_avg + (current_avg - previous_avg), current_avg, 0)::NUMERIC, 1) AS value
            FROM windows
            """,
            "watt",
            6,
            0,
            6,
            7,
            0,
            11000,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 8000}, {"color": "red", "value": 10000}],
            0,
        ),
        gauge_panel(
            p,
            "Peak Outlet Temp",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(MAX(l.outlet_temp_c), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "celsius",
            12,
            0,
            6,
            7,
            20,
            42,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 34}, {"color": "red", "value": 36}],
            1,
        ),
        gauge_panel(
            p,
            "Alert Pressure",
            f"""
            SELECT
              NOW() AS time,
              ROUND(
                COALESCE(
                  SUM(
                    CASE severity
                      WHEN 'critical' THEN 2
                      ELSE 1
                    END
                  ),
                  0
                )::NUMERIC,
                0
              ) AS value
            FROM active_alerts
            WHERE ({ROOM_VAR} = 'All' OR room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR rack_name = {RACK_VAR})
              AND ({SERVER_VAR} = 'All' OR asset_name = {SERVER_VAR})
            """,
            "none",
            18,
            0,
            6,
            7,
            0,
            12,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 3}, {"color": "red", "value": 8}],
            0,
        ),
        timeseries_panel(
            p,
            "Power and Forecast Context",
            f"""
            SELECT
              $__timeGroupAlias(tm.ts, '5m'),
              'Observed Power' AS metric,
              ROUND(SUM(tm.power_w)::NUMERIC, 1) AS value
            FROM telemetry_metrics tm
            JOIN assets a USING (asset_id)
            WHERE $__timeFilter(tm.ts) AND {FILTERS}
            GROUP BY 1
            ORDER BY 1
            """,
            "watt",
            0,
            7,
            12,
            8,
        ),
        timeseries_panel(
            p,
            "CPU and Thermal Drift",
            f"""
            SELECT
              bucket AS time,
              metric,
              value
            FROM (
              SELECT
                $__timeGroup(tm.ts, '5m') AS bucket,
                'CPU %' AS metric,
                ROUND(AVG(tm.cpu_usage)::NUMERIC, 1) AS value
              FROM telemetry_metrics tm
              JOIN assets a USING (asset_id)
              WHERE $__timeFilter(tm.ts) AND {FILTERS}
              GROUP BY 1
              UNION ALL
              SELECT
                $__timeGroup(tm.ts, '5m') AS bucket,
                'Outlet Temp' AS metric,
                ROUND(AVG(tm.outlet_temp_c)::NUMERIC, 1) AS value
              FROM telemetry_metrics tm
              JOIN assets a USING (asset_id)
              WHERE $__timeFilter(tm.ts) AND {FILTERS}
              GROUP BY 1
            ) s
            ORDER BY 1, 2
            """,
            "short",
            12,
            7,
            12,
            8,
        ),
        bargauge_panel(
            p,
            "Rack Stress Score",
            f"""
            SELECT
              a.rack_name AS metric,
              ROUND(AVG(l.cpu_usage) + AVG(l.outlet_temp_c) - 20, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE ({ROOM_VAR} = 'All' OR a.room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR a.rack_name = {RACK_VAR})
            GROUP BY a.rack_name
            ORDER BY value DESC
            """,
            "none",
            0,
            15,
            12,
            8,
            thresholds=[
                {"color": "green", "value": None},
                {"color": "yellow", "value": 75},
                {"color": "red", "value": 95},
            ],
        ),
        table_panel(
            p,
            "Hottest Servers",
            f"""
            SELECT
              a.asset_name AS "Server",
              a.room_name AS "Room",
              a.rack_name AS "Rack",
              ROUND(l.outlet_temp_c::NUMERIC, 1) AS "Outlet C",
              ROUND(l.cpu_usage::NUMERIC, 1) AS "CPU %",
              l.status_level AS "Status"
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            ORDER BY l.outlet_temp_c DESC
            LIMIT 15
            """,
            12,
            15,
            12,
            8,
        ),
        table_panel(
            p,
            "Top Power Servers",
            f"""
            SELECT
              a.asset_name AS "Server",
              a.asset_type AS "Type",
              a.rack_name AS "Rack",
              ROUND(l.power_w::NUMERIC, 0) AS "Power W",
              ROUND(l.cpu_usage::NUMERIC, 1) AS "CPU %",
              ROUND(l.outlet_temp_c::NUMERIC, 1) AS "Outlet C",
              l.operational_state AS "State"
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            ORDER BY l.power_w DESC
            LIMIT 20
            """,
            0,
            23,
            12,
            8,
        ),
        table_panel(
            p,
            "Analytics Alert Feed",
            f"""
            SELECT
              ts AS "Last seen",
              asset_name AS "Asset",
              severity AS "Severity",
              rule_name AS "Signal",
              message AS "Message"
            FROM active_alerts
            WHERE ({ROOM_VAR} = 'All' OR room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR rack_name = {RACK_VAR})
              AND ({SERVER_VAR} = 'All' OR asset_name = {SERVER_VAR})
            ORDER BY ts DESC, severity DESC
            LIMIT 20
            """,
            12,
            23,
            12,
            8,
        ),
    ]
    return dashboard_base("iDT4GDC Analytics", "idt4-analytics", panels)


def carbon_dashboard():
    p = PanelIds()
    panels = [
        gauge_panel(
            p,
            "Current CO2",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(SUM(l.carbon_kg), 0)::NUMERIC, 3) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "suffix:kg CO2e",
            0,
            0,
            6,
            7,
            0,
            0.45,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 0.22}, {"color": "red", "value": 0.35}],
            3,
        ),
        gauge_panel(
            p,
            "Emission Factor",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(AVG(l.emission_factor_kg_per_kwh), 0)::NUMERIC, 3) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "suffix:kg/kWh",
            6,
            0,
            6,
            7,
            0.20,
            0.45,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 0.34}, {"color": "red", "value": 0.40}],
            3,
        ),
        gauge_panel(
            p,
            "Current Power",
            f"""
            SELECT NOW() AS time, ROUND(COALESCE(SUM(l.power_w), 0)::NUMERIC, 1) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            """,
            "watt",
            12,
            0,
            6,
            7,
            0,
            11000,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 7000}, {"color": "red", "value": 9500}],
            0,
        ),
        gauge_panel(
            p,
            "High Carbon Assets",
            f"""
            SELECT NOW() AS time, COUNT(*)::NUMERIC AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
              AND l.carbon_kg >= 0.018
            """,
            "none",
            18,
            0,
            6,
            7,
            0,
            10,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 2}, {"color": "red", "value": 6}],
            0,
        ),
        timeseries_panel(
            p,
            "Estimated Carbon Trend",
            f"""
            SELECT
              $__timeGroupAlias(tm.ts, '5m'),
              'CO2 Estimate' AS metric,
              ROUND(SUM(tm.carbon_kg)::NUMERIC, 3) AS value
            FROM telemetry_metrics tm
            JOIN assets a USING (asset_id)
            WHERE $__timeFilter(tm.ts) AND {FILTERS}
            GROUP BY 1
            ORDER BY 1
            """,
            "suffix:kg CO2e",
            0,
            7,
            12,
            8,
        ),
        timeseries_panel(
            p,
            "Grid Mix and Thermal Context",
            f"""
            SELECT
              bucket AS time,
              metric,
              value
            FROM (
              SELECT
                $__timeGroup(tm.ts, '5m') AS bucket,
                'Emission Factor' AS metric,
                ROUND(AVG(tm.emission_factor_kg_per_kwh)::NUMERIC, 3) AS value
              FROM telemetry_metrics tm
              JOIN assets a USING (asset_id)
              WHERE $__timeFilter(tm.ts) AND {FILTERS}
              GROUP BY 1
              UNION ALL
              SELECT
                $__timeGroup(tm.ts, '5m') AS bucket,
                'Outlet Temp' AS metric,
                ROUND(AVG(tm.outlet_temp_c)::NUMERIC, 1) AS value
              FROM telemetry_metrics tm
              JOIN assets a USING (asset_id)
              WHERE $__timeFilter(tm.ts) AND {FILTERS}
              GROUP BY 1
            ) s
            ORDER BY 1, 2
            """,
            "short",
            12,
            7,
            12,
            8,
        ),
        bargauge_panel(
            p,
            "Rack Carbon Contribution",
            f"""
            SELECT
              a.rack_name AS metric,
              ROUND(SUM(l.carbon_kg)::NUMERIC, 3) AS value
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE ({ROOM_VAR} = 'All' OR a.room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR a.rack_name = {RACK_VAR})
            GROUP BY a.rack_name
            ORDER BY value DESC
            """,
            "suffix:kg CO2e",
            0,
            15,
            12,
            8,
            thresholds=[
                {"color": "green", "value": None},
                {"color": "yellow", "value": 0.10},
                {"color": "red", "value": 0.16},
            ],
        ),
        table_panel(
            p,
            "Top Emitting Assets",
            f"""
            SELECT
              a.asset_name AS "Asset",
              a.rack_name AS "Rack",
              ROUND(l.carbon_kg::NUMERIC, 3) AS "CO2 kg",
              ROUND(l.power_w::NUMERIC, 0) AS "Power W",
              ROUND(l.cpu_usage::NUMERIC, 1) AS "CPU %",
              l.status_level AS "Status"
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE {FILTERS}
            ORDER BY l.carbon_kg DESC
            LIMIT 20
            """,
            12,
            15,
            12,
            8,
        ),
        table_panel(
            p,
            "Carbon Alert Watch",
            f"""
            SELECT
              ts AS "Last seen",
              room_name AS "Room",
              rack_name AS "Rack",
              asset_name AS "Asset",
              severity AS "Severity",
              message AS "Message"
            FROM active_alerts
            WHERE ({ROOM_VAR} = 'All' OR room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR rack_name = {RACK_VAR})
              AND ({SERVER_VAR} = 'All' OR asset_name = {SERVER_VAR})
              AND rule_name IN ('Power spike', 'Thermal envelope', 'Operational state')
            ORDER BY ts DESC, severity DESC
            LIMIT 20
            """,
            0,
            23,
            12,
            8,
        ),
        table_panel(
            p,
            "Room / Rack Footprint",
            f"""
            SELECT
              a.room_name AS "Room",
              a.rack_name AS "Rack",
              COUNT(*) AS "Assets",
              ROUND(SUM(l.power_w)::NUMERIC, 0) AS "Power W",
              ROUND(SUM(l.carbon_kg)::NUMERIC, 3) AS "CO2 kg"
            FROM latest_asset_metrics l
            JOIN assets a USING (asset_id)
            WHERE ({ROOM_VAR} = 'All' OR a.room_name = {ROOM_VAR})
              AND ({RACK_VAR} = 'All' OR a.rack_name = {RACK_VAR})
            GROUP BY a.room_name, a.rack_name
            ORDER BY "CO2 kg" DESC
            """,
            12,
            23,
            12,
            8,
        ),
    ]
    return dashboard_base("iDT4GDC Carbon", "idt4-carbon", panels, time_from="now-24h")


def write_dashboard(filename, dashboard):
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    (DASHBOARD_DIR / filename).write_text(json.dumps(dashboard, indent=2) + "\n")


def main():
    write_dashboard("overview.json", overview_dashboard())
    write_dashboard("analytics.json", analytics_dashboard())
    write_dashboard("carbon.json", carbon_dashboard())


if __name__ == "__main__":
    main()
