import copy
import json
from pathlib import Path
from textwrap import dedent
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "grafana" / "dashboards"
AI_RESULTS_PATH = ROOT / "simulator" / "data" / "ai_model_results.json"
SUSTAINABILITY_KPI_PATH = ROOT / "simulator" / "data" / "sustainability_kpis.json"
DATA_CENTRES_PATH = ROOT / "simulator" / "data" / "data_centres.json"
GPU_FPGA_PATH = ROOT / "simulator" / "data" / "gpu_fpga_acceleration.json"
DATASOURCE = {"type": "postgres", "uid": "postgres-ops"}
PLUGIN_VERSION = "11.0.0"
DATA_CENTRE_VAR = "${data_centre:raw}"
ROOM_VAR = "${room:raw}"
RACK_VAR = "${rack:raw}"
SERVER_VAR = "${server:raw}"
AI_MODEL_VAR = "${ai_model:raw}"
SCENARIO_PHASE_VAR = "${scenario_phase:raw}"
SITE_LOCATION_QP = "${site_location:queryparam}"
SITE_IP_QP = "${site_ip:queryparam}"
USERNAME_QP = "${username:queryparam}"
AI_RESULTS = json.loads(AI_RESULTS_PATH.read_text(encoding="utf-8"))
SUSTAINABILITY_RESULTS = json.loads(SUSTAINABILITY_KPI_PATH.read_text(encoding="utf-8"))
DATA_CENTRES = json.loads(DATA_CENTRES_PATH.read_text(encoding="utf-8"))
GPU_FPGA_RESULTS = json.loads(GPU_FPGA_PATH.read_text(encoding="utf-8"))
def connection_query_params():
    return "&".join(
        [
            "${data_centre:queryparam}",
            SITE_LOCATION_QP,
            SITE_IP_QP,
            USERNAME_QP,
        ]
    )


DEMO_NAV_ITEMS = [
    ("idt4-connect", "Connect Data Centre", f"/d/idt4-connect/connect-data-centre?refresh=10s&{connection_query_params()}"),
    ("idt4-overview", "Overview", f"/d/idt4-overview/idt4gdc-overview?refresh=10s&{connection_query_params()}"),
    ("idt4-analytics", "Analytics", f"/d/idt4-analytics/idt4gdc-analytics?refresh=10s&{connection_query_params()}"),
    ("idt4-carbon", "Carbon", f"/d/idt4-carbon/idt4gdc-carbon?refresh=10s&{connection_query_params()}"),
    ("idt4-sustainability-kpis", "Sustainability KPIs", f"/d/idt4-sustainability-kpis/sustainability-kpis?refresh=10s&{connection_query_params()}"),
    ("idt4-ai-optimisation", "AI Optimisation", f"/d/idt4-ai-optimisation/ai-optimisation?refresh=10s&{connection_query_params()}"),
    ("idt4-gpu-fpga", "GPU–FPGA Acceleration", f"/d/idt4-gpu-fpga/gpu-fpga-acceleration?refresh=10s&{connection_query_params()}"),
]
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


def ai_model_variable():
    query = "SELECT model_name AS __text, quote_literal(model_name) AS __value FROM ai_model_results ORDER BY best_model DESC, preferred_family DESC, model_name"
    return {
        "name": "ai_model",
        "label": "AI Model",
        "type": "query",
        "datasource": DATASOURCE,
        "definition": query,
        "query": query,
        "includeAll": False,
        "multi": False,
        "refresh": 2,
        "sort": 1,
        "current": {"selected": True, "text": "Extended XGBoost", "value": "'Extended XGBoost'"},
    }


def data_centre_variable():
    query = "SELECT dc_name AS __text, quote_literal(dc_name) AS __value FROM data_centre_sources WHERE user_visible = TRUE ORDER BY display_order, dc_name"
    default_name = next(
        (item["name"] for item in DATA_CENTRES["data_centres"] if item["name"] == "Demo Local Data Centre"),
        DATA_CENTRES["data_centres"][0]["name"],
    )
    return {
        "name": "data_centre",
        "label": "Data Centre",
        "type": "query",
        "datasource": DATASOURCE,
        "definition": query,
        "query": query,
        "includeAll": False,
        "multi": False,
        "refresh": 2,
        "sort": 1,
        "current": {"selected": True, "text": default_name, "value": f"'{default_name}'"},
    }


def ip_address_variable():
    query = dedent(
        f"""
        SELECT ip_address AS __text, quote_literal(ip_address) AS __value
        FROM data_centre_sources
        WHERE dc_name = {DATA_CENTRE_VAR}
        ORDER BY display_order
        """
    ).strip()
    default_ip = next(
        (item["ip_address"] for item in DATA_CENTRES["data_centres"] if item["name"] == "Demo Local Data Centre"),
        DATA_CENTRES["data_centres"][0]["ip_address"],
    )
    return {
        "name": "ip_address",
        "label": "IP Address",
        "type": "query",
        "datasource": DATASOURCE,
        "definition": query,
        "query": query,
        "includeAll": False,
        "multi": False,
        "refresh": 2,
        "sort": 1,
        "current": {"selected": True, "text": default_ip, "value": f"'{default_ip}'"},
    }


def textbox_variable(name, label, default_value):
    return {
        "name": name,
        "label": label,
        "type": "textbox",
        "query": default_value,
        "current": {"selected": True, "text": default_value, "value": default_value},
        "options": [{"selected": True, "text": default_value, "value": default_value}],
    }


def connection_context_variables(include_password=False, hidden=False):
    vars_list = [
        data_centre_variable(),
        textbox_variable("site_location", "Location", "Local Simulation"),
        textbox_variable("site_ip", "IP Address", "127.0.0.1"),
        textbox_variable("username", "Username", "bitnet"),
    ]
    if include_password:
        vars_list.append(textbox_variable("password", "Password", "datatwin"))
    if hidden:
        for variable in vars_list:
            if variable["name"] != "data_centre":
                variable["hide"] = 2
    return vars_list


def scenario_phase_variable():
    query = dedent(
        """
        SELECT 'Baseline' AS __text, quote_literal('baseline') AS __value
        UNION ALL SELECT 'Running', quote_literal('running')
        UNION ALL SELECT 'Scheduler Active', quote_literal('scheduler')
        UNION ALL SELECT 'GPU Training', quote_literal('gpu_training')
        UNION ALL SELECT 'FPGA Inference', quote_literal('fpga_inference')
        UNION ALL SELECT 'Optimised', quote_literal('optimised')
        """
    ).strip()
    return {
        "name": "scenario_phase",
        "label": "Simulation Phase",
        "type": "query",
        "datasource": DATASOURCE,
        "definition": query,
        "query": query,
        "includeAll": False,
        "multi": False,
        "refresh": 1,
        "sort": 0,
        "current": {"selected": True, "text": "Baseline", "value": "'baseline'"},
    }


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


def dashboard_base(title, uid, panels, time_from="now-6h", include_scope_filters=True, extra_variables=None):
    variables = []
    if extra_variables:
        variables.extend(extra_variables)
    if include_scope_filters:
        variables.extend([room_variable(), rack_variable(), server_variable()])
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
        "templating": {"list": variables},
        "time": {"from": time_from, "to": "now"},
        "timepicker": {},
        "timezone": "",
        "title": title,
        "uid": uid,
        "version": 1,
        "weekStart": "",
    }


def demo_nav_content(current_uid):
    items = []
    for uid, label, href in DEMO_NAV_ITEMS:
        if uid == current_uid:
            items.append(
                f'<div style="padding:10px 12px; margin:6px 0; border-radius:10px; background:#1f2937; color:#ffffff; font-weight:700;">{label}</div>'
            )
        else:
            items.append(
                f'<a href="{href}" style="display:block; padding:10px 12px; margin:6px 0; border-radius:10px; background:#111827; color:#d7dee9; text-decoration:none; font-weight:600;">{label}</a>'
            )
    return dedent(
        f"""
        <div style="display:flex; flex-direction:column; height:100%; padding:6px 4px;">
          <div style="font-size:24px; font-weight:800; color:#f3f6fb; letter-spacing:0.01em; margin-bottom:4px;">iDT4GDC</div>
          <div style="font-size:12px; text-transform:uppercase; letter-spacing:0.16em; color:#8aa1c7; margin-bottom:14px;">Demo Navigation</div>
          {''.join(items)}
          <div style="margin-top:auto; padding-top:16px; color:#93a1b5; font-size:12px; line-height:1.5;">
            Use the top selectors to set the active site and the Grafana time picker to change the analysis window.
          </div>
        </div>
        """
    ).strip()


def preset_profile_cards():
    cards = []
    for item in DATA_CENTRES["data_centres"]:
        if not item.get("user_visible", True):
            continue
        quoted_name = quote(f"'{item['name']}'", safe="")
        href = (
            "/d/idt4-connect/connect-data-centre?refresh=10s"
            f"&var-data_centre={quoted_name}"
            f"&var-site_location={quote(item['location'], safe='')}"
            f"&var-site_ip={quote(item['ip_address'], safe='')}"
            f"&var-username={quote(item['default_username'], safe='')}"
            f"&var-password={quote(item['default_password'], safe='')}"
        )
        cards.append(
            dedent(
                f"""
                <a href="{href}" style="display:block; padding:14px; border-radius:14px; background:#111827; border:1px solid #243244; color:#e5edf8; text-decoration:none;">
                  <div style="font-size:16px; font-weight:700; color:#ffffff; margin-bottom:6px;">{item['name']}</div>
                  <div style="font-size:13px; color:#93a1b5; line-height:1.5;">{item['location']}</div>
                  <div style="font-size:13px; color:#93a1b5;">{item['ip_address']} · {item['source_type']}</div>
                  <div style="margin-top:10px; display:inline-block; padding:8px 12px; border-radius:10px; background:#1d4ed8; color:#ffffff; font-size:12px; font-weight:700;">Use Profile</div>
                </a>
                """
            ).strip()
        )
    return dedent(
        f"""
        <div style="display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px;">
          {''.join(cards)}
        </div>
        """
    ).strip()


def with_demo_nav(panel_ids, panels, current_uid):
    max_height = max((panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in panels), default=12)
    remapped = []
    for panel in panels:
        cloned = copy.deepcopy(panel)
        x = cloned["gridPos"]["x"]
        w = cloned["gridPos"]["w"]
        new_x = 4 + round(x * 20 / 24)
        new_right = 4 + round((x + w) * 20 / 24)
        cloned["gridPos"]["x"] = new_x
        cloned["gridPos"]["w"] = max(1, new_right - new_x)
        remapped.append(cloned)

    nav_panel = {
        "datasource": DATASOURCE,
        "gridPos": {"h": max_height, "w": 4, "x": 0, "y": 0},
        "id": panel_ids.next(),
        "options": {
            "content": demo_nav_content(current_uid),
            "mode": "html",
        },
        "pluginVersion": PLUGIN_VERSION,
        "title": "",
        "transparent": True,
        "type": "text",
    }
    return [nav_panel] + remapped


def shift_panels(panels, delta_y):
    shifted = []
    for panel in panels:
        cloned = copy.deepcopy(panel)
        cloned["gridPos"]["y"] += delta_y
        shifted.append(cloned)
    return shifted


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


def text_panel(panel_ids, title, content, x, y, w, h, transparent=False):
    return {
        "datasource": DATASOURCE,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_ids.next(),
        "options": {
            "content": content,
            "mode": "markdown",
        },
        "pluginVersion": PLUGIN_VERSION,
        "title": title,
        "transparent": transparent,
        "type": "text",
    }


def barchart_panel(panel_ids, title, sql, x, y, w, h, orientation="vertical"):
    return {
        "datasource": DATASOURCE,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {
                    "axisBorderShow": False,
                    "axisCenteredZero": False,
                    "axisColorMode": "text",
                    "axisPlacement": "auto",
                    "fillOpacity": 80,
                    "gradientMode": "none",
                    "lineWidth": 1,
                    "scaleDistribution": {"type": "linear"},
                },
                "mappings": [],
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
            },
            "overrides": [],
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": panel_ids.next(),
        "options": {
            "barRadius": 0,
            "barWidth": 0.8,
            "fullHighlight": False,
            "groupWidth": 0.7,
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "orientation": orientation,
            "showValue": "auto",
            "stacking": "none",
            "tooltip": {"mode": "single", "sort": "none"},
            "xTickLabelRotation": 0,
            "xTickLabelSpacing": 0,
        },
        "pluginVersion": PLUGIN_VERSION,
        "targets": [target(sql)],
        "title": title,
        "type": "barchart",
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


def connect_data_centre_dashboard():
    p = PanelIds()
    connect_button = (
        f'<a href="/d/idt4-overview/idt4gdc-overview?refresh=10s&{connection_query_params()}" '
        'style="display:inline-block; padding:12px 20px; border-radius:10px; background:#2563eb; color:#ffffff; '
        'text-decoration:none; font-weight:700; margin-top:12px;">Connect</a>'
    )
    panels = [
        text_panel(
            p,
            "Connect Data Centre",
            dedent(
                f"""
                <div style="padding:10px 4px;">
                  <div style="font-size:30px; font-weight:800; color:#f3f6fb; margin-bottom:8px;">Connect Data Centre</div>
                  <div style="color:#c5cfdd; font-size:15px; line-height:1.6;">
                    Choose a profile preset or edit the variables above, then connect as if the platform has authenticated against a live data-centre telemetry stream.
                  </div>
                  <div style="margin-top:16px; padding:16px; border-radius:14px; background:#111827; border:1px solid #243244;">
                    <div style="font-size:12px; text-transform:uppercase; letter-spacing:0.16em; color:#8aa1c7;">Current connection target</div>
                    <div style="font-size:24px; font-weight:800; color:#ffffff; margin-top:4px;">${{data_centre:text}}</div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:14px;">
                      <div><div style="font-size:12px; color:#8aa1c7;">Location</div><div style="font-size:18px; color:#ffffff;">${{site_location}}</div></div>
                      <div><div style="font-size:12px; color:#8aa1c7;">IP address</div><div style="font-size:18px; color:#ffffff;">${{site_ip}}</div></div>
                      <div><div style="font-size:12px; color:#8aa1c7;">Username</div><div style="font-size:18px; color:#ffffff;">${{username}}</div></div>
                      <div><div style="font-size:12px; color:#8aa1c7;">Password</div><div style="font-size:18px; color:#ffffff;">${{password}}</div></div>
                      <div><div style="font-size:12px; color:#8aa1c7;">Authentication</div><div style="font-size:18px; color:#34d399;">Mock JWT ready</div></div>
                      <div><div style="font-size:12px; color:#8aa1c7;">Stream status</div><div style="font-size:18px; color:#34d399;">Telemetry stream waiting for connect</div></div>
                    </div>
                    <div style="margin-top:12px; color:#fbbf24;">⏳ Simulated handshake, JWT validation, and stream negotiation</div>
                    {connect_button}
                  </div>
                </div>
                """
            ).strip(),
            0,
            0,
            12,
            9,
        ),
        text_panel(
            p,
            "Profile Presets",
            dedent(
                f"""
                <div style="padding:8px 4px;">
                  <div style="font-size:24px; font-weight:800; color:#f3f6fb; margin-bottom:8px;">Profile Presets</div>
                  <div style="color:#c5cfdd; font-size:14px; line-height:1.5; margin-bottom:14px;">
                    Use one of the prepared profiles below to prefill the fake connection fields, or adjust the variable controls manually.
                  </div>
                  {preset_profile_cards()}
                </div>
                """
            ).strip(),
            12,
            0,
            12,
            9,
        ),
        table_panel(
            p,
            "Available Data Centre Profiles",
            """
            SELECT
              dc_name AS "Data centre",
              location AS "Location",
              ip_address AS "IP address",
              source_type AS "Source type",
              default_username AS "Username"
            FROM data_centre_sources
            WHERE user_visible = TRUE
            ORDER BY display_order
            """,
            0,
            9,
            12,
            8,
        ),
        table_panel(
            p,
            "Selected Profile Status",
            f"""
            SELECT
              dc_name AS "Profile",
              location AS "Location",
              ip_address AS "Default IP",
              source_type AS "Source type",
              default_username AS "Default username",
              jwt_status AS "JWT token",
              stream_status AS "Data stream",
              last_sync AS "Last sync"
            FROM latest_connection_status
            WHERE dc_name = {DATA_CENTRE_VAR}
            """,
            12,
            9,
            12,
            8,
        ),
        table_panel(
            p,
            "Demo Registry / Added Profiles",
            """
            SELECT
              dc_name AS "Data centre",
              location AS "Location",
              ip_address AS "IP address",
              source_type AS "Source type",
              user_added AS "User added"
            FROM data_centre_sources
            WHERE user_added = TRUE
            ORDER BY display_order
            """,
            0,
            17,
            24,
            6,
        ),
    ]
    return dashboard_base(
        "Connect Data Centre",
        "idt4-connect",
        with_demo_nav(p, panels, "idt4-connect"),
        time_from="now-6h",
        include_scope_filters=False,
        extra_variables=connection_context_variables(include_password=True),
    )


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
    top_panels = [
        text_panel(
            p,
            "Connected Data Centre",
            dedent(
                """
                ### Connected Data Centre

                - **Profile:** ${data_centre:text}
                - **Location:** ${site_location}
                - **IP address:** ${site_ip}
                - **Connection status:** Connected
                - **JWT token:** Valid
                - **Data stream:** Reading metrics
                - **Tip:** use the Grafana time-range selector for `Last 1 hour`, `Last 3 hours`, `Last 24 hours`, or `Last 30 days`.
                """
            ).strip(),
            0,
            0,
            8,
            4,
        ),
        stat_panel(
            p,
            "Last Sync",
            """
            SELECT last_sync AS time, EXTRACT(EPOCH FROM last_sync)::NUMERIC AS value
            FROM latest_connection_status
            WHERE dc_name = ${data_centre:raw}
            """,
            "dateTimeAsIso",
            8,
            0,
            4,
            4,
        ),
        stat_panel(
            p,
            "Avg Power",
            """
            SELECT NOW() AS time, ROUND(AVG(total_facility_power_w)::NUMERIC, 1) AS value
            FROM sustainability_kpi_snapshots
            WHERE $__timeFilter(ts)
            """,
            "watt",
            12,
            0,
            4,
            4,
        ),
        stat_panel(
            p,
            "Avg Carbon",
            """
            SELECT NOW() AS time, ROUND(AVG(total_co2_kg)::NUMERIC, 3) AS value
            FROM sustainability_kpi_snapshots
            WHERE $__timeFilter(ts)
            """,
            "suffix:kg CO2e",
            16,
            0,
            4,
            4,
        ),
        stat_panel(
            p,
            "Avg PPW",
            """
            SELECT NOW() AS time, ROUND(AVG(ppw)::NUMERIC, 3) AS value
            FROM sustainability_kpi_snapshots
            WHERE $__timeFilter(ts)
            """,
            "suffix: perf/W",
            20,
            0,
            4,
            4,
        ),
    ]
    combined = top_panels + shift_panels(panels, 4)
    return dashboard_base(
        "iDT4GDC Overview",
        "idt4-overview",
        with_demo_nav(p, combined, "idt4-overview"),
        extra_variables=connection_context_variables(hidden=True),
    )


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
    return dashboard_base(
        "iDT4GDC Analytics",
        "idt4-analytics",
        with_demo_nav(p, panels, "idt4-analytics"),
        extra_variables=connection_context_variables(hidden=True),
    )


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
    return dashboard_base(
        "iDT4GDC Carbon",
        "idt4-carbon",
        with_demo_nav(p, panels, "idt4-carbon"),
        time_from="now-24h",
        extra_variables=connection_context_variables(hidden=True),
    )


def sustainability_kpis_dashboard():
    p = PanelIds()
    outcome_statement = SUSTAINABILITY_RESULTS["outcome_statement"]

    panels = [
        text_panel(
            p,
            "Sustainability KPIs",
            dedent(
                f"""
                ## Sustainability KPIs

                This dashboard translates D3.2 sustainability indicators into a demo-friendly operations view. It connects energy, carbon, renewable availability, and efficiency KPIs back to the simulated data-centre telemetry stream.

                **Outcome**

                {outcome_statement}
                """
            ).strip(),
            0,
            0,
            24,
            4,
        ),
        stat_panel(
            p,
            "PUE",
            """
            SELECT NOW() AS time, ROUND(pue::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "none",
            0,
            4,
            4,
            4,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 1.35}, {"color": "red", "value": 1.55}],
        ),
        stat_panel(
            p,
            "REF",
            """
            SELECT NOW() AS time, ROUND(ref::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "percentunit",
            4,
            4,
            4,
            4,
            [{"color": "red", "value": None}, {"color": "yellow", "value": 0.35}, {"color": "green", "value": 0.55}],
        ),
        stat_panel(
            p,
            "ERF",
            """
            SELECT NOW() AS time, ROUND(erf::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "percentunit",
            8,
            4,
            4,
            4,
            [{"color": "red", "value": None}, {"color": "yellow", "value": 0.10}, {"color": "green", "value": 0.20}],
        ),
        stat_panel(
            p,
            "CEF",
            """
            SELECT NOW() AS time, ROUND(cef::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "suffix:kg/kWh",
            12,
            4,
            4,
            4,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 0.32}, {"color": "red", "value": 0.40}],
        ),
        stat_panel(
            p,
            "CO2 Savings",
            """
            SELECT NOW() AS time, ROUND(co2_savings_kg::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "suffix:kg CO2e",
            16,
            4,
            4,
            4,
            [{"color": "red", "value": None}, {"color": "yellow", "value": 0.30}, {"color": "green", "value": 0.60}],
        ),
        stat_panel(
            p,
            "PPW",
            """
            SELECT NOW() AS time, ROUND(ppw::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "suffix: perf/W",
            20,
            4,
            4,
            4,
            [{"color": "red", "value": None}, {"color": "yellow", "value": 1.60}, {"color": "green", "value": 2.20}],
        ),
        gauge_panel(
            p,
            "PUE",
            """
            SELECT NOW() AS time, ROUND(pue::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "none",
            0,
            8,
            6,
            7,
            1.0,
            1.8,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 1.35}, {"color": "red", "value": 1.55}],
            3,
        ),
        gauge_panel(
            p,
            "REF",
            """
            SELECT NOW() AS time, ROUND(ref::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "percentunit",
            6,
            8,
            6,
            7,
            0,
            1,
            [{"color": "red", "value": None}, {"color": "yellow", "value": 0.35}, {"color": "green", "value": 0.55}],
            2,
        ),
        gauge_panel(
            p,
            "CUE",
            """
            SELECT NOW() AS time, ROUND(cue::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "suffix:kg/kWh",
            12,
            8,
            6,
            7,
            0.20,
            0.80,
            [{"color": "green", "value": None}, {"color": "yellow", "value": 0.42}, {"color": "red", "value": 0.55}],
            3,
        ),
        gauge_panel(
            p,
            "PPW",
            """
            SELECT NOW() AS time, ROUND(ppw::NUMERIC, 3) AS value
            FROM latest_sustainability_snapshot
            """,
            "suffix: perf/W",
            18,
            8,
            6,
            7,
            0.5,
            3.5,
            [{"color": "red", "value": None}, {"color": "yellow", "value": 1.60}, {"color": "green", "value": 2.20}],
            3,
        ),
        timeseries_panel(
            p,
            "PUE Trend",
            """
            SELECT
              $__timeGroupAlias(ts, '5m'),
              'PUE' AS metric,
              ROUND(AVG(pue)::NUMERIC, 3) AS value
            FROM sustainability_kpi_snapshots
            WHERE $__timeFilter(ts)
            GROUP BY 1
            ORDER BY 1
            """,
            "none",
            0,
            15,
            12,
            8,
        ),
        timeseries_panel(
            p,
            "CO2 Emissions Trend",
            """
            SELECT
              $__timeGroupAlias(ts, '5m'),
              'CO2 Emissions' AS metric,
              ROUND(AVG(total_co2_kg)::NUMERIC, 3) AS value
            FROM sustainability_kpi_snapshots
            WHERE $__timeFilter(ts)
            GROUP BY 1
            ORDER BY 1
            """,
            "suffix:kg CO2e",
            12,
            15,
            12,
            8,
        ),
        timeseries_panel(
            p,
            "REF Trend",
            """
            SELECT
              $__timeGroupAlias(ts, '5m'),
              'REF' AS metric,
              ROUND(AVG(ref)::NUMERIC, 3) AS value
            FROM sustainability_kpi_snapshots
            WHERE $__timeFilter(ts)
            GROUP BY 1
            ORDER BY 1
            """,
            "percentunit",
            0,
            23,
            12,
            8,
        ),
        timeseries_panel(
            p,
            "CO2 Savings Trend",
            """
            SELECT
              $__timeGroupAlias(ts, '5m'),
              'CO2 Savings' AS metric,
              ROUND(AVG(co2_savings_kg)::NUMERIC, 3) AS value
            FROM sustainability_kpi_snapshots
            WHERE $__timeFilter(ts)
            GROUP BY 1
            ORDER BY 1
            """,
            "suffix:kg CO2e",
            12,
            23,
            12,
            8,
        ),
        barchart_panel(
            p,
            "Baseline vs Current CO2",
            """
            SELECT metric, value
            FROM (
              SELECT 'Baseline CO2' AS metric, ROUND(baseline_co2_kg::NUMERIC, 3) AS value
              FROM latest_sustainability_snapshot
              UNION ALL
              SELECT 'Current CO2' AS metric, ROUND(total_co2_kg::NUMERIC, 3) AS value
              FROM latest_sustainability_snapshot
            ) s
            """,
            0,
            31,
            12,
            8,
        ),
        bargauge_panel(
            p,
            "Advanced KPI Section",
            """
            SELECT metric, value
            FROM (
              SELECT 'HUE' AS metric, ROUND(hue::NUMERIC, 3) AS value FROM latest_sustainability_snapshot
              UNION ALL
              SELECT 'SHE' AS metric, ROUND(she::NUMERIC, 3) AS value FROM latest_sustainability_snapshot
              UNION ALL
              SELECT 'APCren' AS metric, ROUND(apcren::NUMERIC, 3) AS value FROM latest_sustainability_snapshot
              UNION ALL
              SELECT 'DCA' AS metric, ROUND(dca::NUMERIC, 3) AS value FROM latest_sustainability_snapshot
            ) advanced
            """,
            "none",
            12,
            31,
            12,
            8,
            thresholds=[
                {"color": "red", "value": None},
                {"color": "yellow", "value": 0.55},
                {"color": "green", "value": 0.72},
            ],
        ),
        table_panel(
            p,
            "KPI Interpretation Guide",
            """
            SELECT
              label AS "KPI",
              CASE
                WHEN direction = 'higher' THEN 'Higher is better'
                ELSE 'Lower is better'
              END AS "Target",
              interpretation AS "Interpretation"
            FROM sustainability_kpi_metadata
            ORDER BY is_advanced, display_order
            """,
            0,
            39,
            24,
            7,
        ),
        table_panel(
            p,
            "Mock Sustainability Metric Export",
            """
            SELECT
              ts AS "Timestamp",
              metric_name AS "Metric",
              ROUND(metric_value::NUMERIC, 4) AS "Value"
            FROM sustainability_prom_metrics
            ORDER BY metric_name
            """,
            0,
            46,
            12,
            6,
        ),
        text_panel(
            p,
            "Operational Interpretation",
            dedent(
                """
                ### Operational interpretation

                - **PUE / CUE / CEF** indicate how efficiently and cleanly the facility is operating.
                - **REF / ERF / CO2 Savings** indicate how strongly the site benefits from renewable supply and recoverable energy reuse.
                - **PPW** shows whether the platform is delivering more useful work per unit of power.
                - **HUE / SHE / APCren / DCA** provide a forward-looking sustainability layer that links thermal reuse and renewable-aware adaptability to day-to-day operations.
                """
            ).strip(),
            12,
            46,
            12,
            6,
        ),
        bargauge_panel(
            p,
            "Average Metrics",
            """
            SELECT metric, value
            FROM (
              SELECT 'Avg PUE' AS metric, ROUND(AVG(pue)::NUMERIC, 3) AS value FROM sustainability_kpi_snapshots WHERE $__timeFilter(ts)
              UNION ALL
              SELECT 'Avg REF', ROUND(AVG(ref)::NUMERIC, 3) FROM sustainability_kpi_snapshots WHERE $__timeFilter(ts)
              UNION ALL
              SELECT 'Avg ERF', ROUND(AVG(erf)::NUMERIC, 3) FROM sustainability_kpi_snapshots WHERE $__timeFilter(ts)
              UNION ALL
              SELECT 'Avg CUE', ROUND(AVG(cue)::NUMERIC, 3) FROM sustainability_kpi_snapshots WHERE $__timeFilter(ts)
              UNION ALL
              SELECT 'Avg CO2 savings', ROUND(AVG(co2_savings_kg)::NUMERIC, 3) FROM sustainability_kpi_snapshots WHERE $__timeFilter(ts)
              UNION ALL
              SELECT 'Avg PPW', ROUND(AVG(ppw)::NUMERIC, 3) FROM sustainability_kpi_snapshots WHERE $__timeFilter(ts)
            ) averages
            """,
            "none",
            0,
            52,
            12,
            8,
            thresholds=[
                {"color": "red", "value": None},
                {"color": "yellow", "value": 0.35},
                {"color": "green", "value": 0.65},
            ],
        ),
        table_panel(
            p,
            "Average Metrics Detail",
            """
            SELECT
              ROUND(AVG(pue)::NUMERIC, 3) AS "Avg PUE",
              ROUND(AVG(ref)::NUMERIC, 3) AS "Avg REF",
              ROUND(AVG(erf)::NUMERIC, 3) AS "Avg ERF",
              ROUND(AVG(cue)::NUMERIC, 3) AS "Avg CUE",
              ROUND(AVG(co2_savings_kg)::NUMERIC, 3) AS "Avg CO2 savings",
              ROUND(AVG(ppw)::NUMERIC, 3) AS "Avg PPW",
              ROUND(AVG(total_facility_power_w)::NUMERIC, 1) AS "Avg power",
              ROUND(AVG(total_co2_kg)::NUMERIC, 3) AS "Avg carbon"
            FROM sustainability_kpi_snapshots
            WHERE $__timeFilter(ts)
            """,
            12,
            52,
            12,
            8,
        ),
    ]
    return dashboard_base(
        "Sustainability KPIs",
        "idt4-sustainability-kpis",
        with_demo_nav(p, panels, "idt4-sustainability-kpis"),
        time_from="now-24h",
        include_scope_filters=False,
        extra_variables=connection_context_variables(hidden=True),
    )


def model_summary_markdown(model):
    accuracy = f"{model['accuracy_percent']:.2f}%" if model.get("accuracy_percent") is not None else "N/A"
    energy = f"{model['energy_j']} J" if model.get("energy_j") is not None else "N/A"
    badges = []
    if model.get("best_model"):
        badges.append("**Best overall**")
    if model.get("preferred_family"):
        badges.append("**Preferred family**")
    badge_line = " · ".join(badges) if badges else "Telemetry-driven benchmark"
    return dedent(
        f"""
        ### {model['name']}
        {badge_line}

        - **Type:** {model['type']}
        - **Purpose:** {model['purpose']}
        - **Accuracy:** {accuracy}
        - **Energy:** {energy}
        - **Interpretation:** {model['interpretation']}
        """
    ).strip()


def ai_optimisation_dashboard():
    p = PanelIds()
    model_cards = AI_RESULTS["models"]
    outcome_statement = AI_RESULTS["outcome_statement"]

    panels = [
        text_panel(
            p,
            "AI Energy Optimisation",
            dedent(
                f"""
                ## AI Energy Optimisation

                The original D3.3 direction targeted water-based heat reuse and water regime optimisation. In the absence of a suitable liquid-cooled testbed, the work was redirected toward **AI-based telemetry modelling** for predictive energy management.

                This view shows how telemetry-driven models can support **energy-aware workload orchestration** and **predictive energy management** using currently available server signals.
                """
            ).strip(),
            0,
            0,
            24,
            4,
        ),
    ]

    positions = [(0, 4), (6, 4), (12, 4), (18, 4)]
    for model, (x, y) in zip(model_cards, positions):
        panels.append(text_panel(p, model["name"], model_summary_markdown(model), x, y, 6, 7))

    panels.extend(
        [
            barchart_panel(
                p,
                "Energy Consumption by Model",
                """
                SELECT
                  model_name AS "Model",
                  ROUND(energy_j::NUMERIC, 0) AS "Energy (J)"
                FROM ai_model_results
                ORDER BY energy_j DESC NULLS LAST
                """,
                0,
                11,
                12,
                8,
            ),
            text_panel(
                p,
                "Preferred Model Family",
                dedent(
                    """
                    ### Preferred model family

                    - **Extended XGBoost** achieved the best numerical accuracy and stability.
                    - **XGBoost** delivered the strongest balance between predictive quality and low energy demand.
                    - The XGBoost family is therefore the preferred decision support option for energy-aware orchestration.
                    """
                ).strip(),
                12,
                11,
                12,
                8,
            ),
            barchart_panel(
                p,
                "Accuracy vs Energy Trade-off",
                """
                WITH bounds AS (
                  SELECT MIN(energy_j) AS min_energy, MAX(energy_j) AS max_energy
                  FROM ai_model_results
                )
                SELECT
                  r.model_name AS "Model",
                  ROUND(r.accuracy_percent::NUMERIC, 2) AS "Accuracy (%)",
                  ROUND(
                    (
                      100 * (
                        1 - ((r.energy_j - b.min_energy) / NULLIF(b.max_energy - b.min_energy, 0))
                      )
                    )::NUMERIC,
                    2
                  ) AS "Energy Efficiency Index"
                FROM ai_model_results r
                CROSS JOIN bounds b
                ORDER BY r.best_model DESC, r.preferred_family DESC, r.accuracy_percent DESC
                """,
                0,
                19,
                12,
                8,
            ),
            timeseries_panel(
                p,
                "Actual vs Predicted Power",
                f"""
                SELECT
                  $__timeGroupAlias(tm.ts, '5m'),
                  'Actual Power' AS metric,
                  ROUND(SUM(tm.power_w)::NUMERIC, 1) AS value
                FROM telemetry_metrics tm
                WHERE $__timeFilter(tm.ts)
                GROUP BY 1

                UNION ALL

                SELECT
                  $__timeGroupAlias(tm.ts, '5m'),
                  'Predicted Power' AS metric,
                  ROUND(
                    SUM(
                      CASE
                        WHEN {AI_MODEL_VAR} = 'LSTM' THEN tm.power_w * 1.018 + tm.cpu_usage * 1.85 + (tm.outlet_temp_c - tm.inlet_temp_c) * 2.10 + ((tm.inlet_temp_c - 1.6) * 0.70)
                        WHEN {AI_MODEL_VAR} = 'Random Forest' THEN tm.power_w * 1.004 + tm.cpu_usage * 1.10 + (tm.outlet_temp_c - tm.inlet_temp_c) * 1.60 + ((tm.inlet_temp_c - 1.6) * 0.55)
                        WHEN {AI_MODEL_VAR} = 'Extended XGBoost' THEN tm.power_w * 0.995 + tm.cpu_usage * 0.72 + (tm.outlet_temp_c - tm.inlet_temp_c) * 1.18 + ((tm.inlet_temp_c - 1.6) * 0.42)
                        ELSE tm.power_w * 0.998 + tm.cpu_usage * 0.84 + (tm.outlet_temp_c - tm.inlet_temp_c) * 1.35 + ((tm.inlet_temp_c - 1.6) * 0.48)
                      END
                    )::NUMERIC,
                    1
                  ) AS value
                FROM telemetry_metrics tm
                WHERE $__timeFilter(tm.ts)
                GROUP BY 1
                ORDER BY 1
                """,
                "watt",
                12,
                19,
                12,
                8,
            ),
            table_panel(
                p,
                "Telemetry Feature Inputs",
                """
                SELECT
                  feature_name AS "Feature",
                  description AS "Why it matters"
                FROM ai_model_features
                ORDER BY display_order
                """,
                0,
                27,
                12,
                8,
            ),
            barchart_panel(
                p,
                "XGBoost Feature Importance",
                """
                SELECT
                  fi.feature_name AS "Feature",
                  ROUND(fi.importance_score::NUMERIC, 3) AS "Importance"
                FROM ai_feature_importance fi
                WHERE fi.model_name = 'XGBoost'
                ORDER BY fi.importance_score DESC
                """,
                12,
                27,
                12,
                8,
                orientation="horizontal",
            ),
            text_panel(
                p,
                "AI Outcome Panel",
                dedent(
                    f"""
                    ## AI Outcome Panel

                    {outcome_statement}

                    **Interpretation**

                    The AI layer does not replace infrastructure telemetry. Instead, it converts telemetry into a predictive control signal that can guide workload placement, reduce unnecessary energy overhead, and support constrained data-centre operations when physical heat-reuse experimentation is not available.
                    """
                ).strip(),
                0,
                35,
                24,
                6,
            ),
        ]
    )

    return dashboard_base(
        "AI Optimisation",
        "idt4-ai-optimisation",
        with_demo_nav(p, panels, "idt4-ai-optimisation"),
        time_from="now-6h",
        include_scope_filters=False,
        extra_variables=connection_context_variables(hidden=True) + [ai_model_variable()],
    )


def gpu_fpga_acceleration_dashboard():
    p = PanelIds()
    workload = GPU_FPGA_RESULTS["workload"]
    scenario = GPU_FPGA_RESULTS["scenario"]
    controls_html = dedent(
        f"""
        <div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:8px;">
          <a href="/d/idt4-gpu-fpga/gpu-fpga-acceleration?refresh=10s&{connection_query_params()}&var-scenario_phase=%27running%27" style="display:inline-block; padding:10px 16px; border-radius:10px; background:#2563eb; color:#fff; text-decoration:none; font-weight:700;">Start</a>
          <a href="/d/idt4-gpu-fpga/gpu-fpga-acceleration?refresh=10s&{connection_query_params()}&var-scenario_phase=%27scheduler%27" style="display:inline-block; padding:10px 16px; border-radius:10px; background:#475569; color:#fff; text-decoration:none; font-weight:700;">Pause</a>
          <a href="/d/idt4-gpu-fpga/gpu-fpga-acceleration?refresh=10s&{connection_query_params()}&var-scenario_phase=%27optimised%27" style="display:inline-block; padding:10px 16px; border-radius:10px; background:#0f766e; color:#fff; text-decoration:none; font-weight:700;">Fast Forward</a>
          <a href="/d/idt4-gpu-fpga/gpu-fpga-acceleration?refresh=10s&{connection_query_params()}&var-scenario_phase=%27baseline%27" style="display:inline-block; padding:10px 16px; border-radius:10px; background:#7c2d12; color:#fff; text-decoration:none; font-weight:700;">Reset</a>
        </div>
        """
    ).strip()

    panels = [
        text_panel(
            p,
            "Workload Summary",
            dedent(
                f"""
                ### Workload Summary Card

                - **Workload:** {workload['name']}
                - **Model:** {workload['model']}
                - **Goal:** {workload['goal']}
                - **Hardware backends:** {', '.join(workload['hardware_backends'])}
                """
            ).strip(),
            0,
            0,
            8,
            6,
        ),
        text_panel(
            p,
            "AI Scheduler / Placement",
            dedent(
                """
                <div style="display:flex; flex-direction:column; gap:10px;">
                  <div style="padding:12px; border-radius:12px; background:#111827; border:1px solid #243244;"><strong>CPU</strong> → Data handling / preprocessing</div>
                  <div style="padding:12px; border-radius:12px; background:#111827; border:1px solid #243244;"><strong>GPU</strong> → XGBoost training / model building</div>
                  <div style="padding:12px; border-radius:12px; background:#111827; border:1px solid #243244;"><strong>FPGA</strong> → Real-time inference / fraud scoring</div>
                  <div style="color:#c5cfdd; line-height:1.6; margin-top:4px;">AI-based scheduler evaluates workload type, latency target, and energy budget, then places training on GPU and low-latency inference on FPGA.</div>
                </div>
                """
            ).strip(),
            8,
            0,
            8,
            6,
        ),
        text_panel(
            p,
            "Simulation Controls",
            dedent(
                f"""
                ### Simulation Controls

                - **Current phase:** ${{scenario_phase:text}}
                - **Connected profile:** ${{data_centre:text}}
                - **Scenario flow:** CPU baseline → scheduler activation → GPU training → FPGA inference → optimised operation

                {controls_html}
                """
            ).strip(),
            16,
            0,
            8,
            6,
        ),
        stat_panel(
            p,
            "FPGA Inference Speed-up",
            "SELECT NOW() AS time, fpga_inference_speedup::NUMERIC AS value FROM gpu_fpga_scenario",
            "suffix:x",
            0,
            6,
            6,
            4,
        ),
        stat_panel(
            p,
            "FPGA Performance / Watt",
            "SELECT NOW() AS time, fpga_perf_per_watt::NUMERIC AS value FROM gpu_fpga_scenario",
            "suffix:x baseline",
            6,
            6,
            6,
            4,
        ),
        stat_panel(
            p,
            "Energy Saving",
            "SELECT NOW() AS time, energy_saving_percent::NUMERIC AS value FROM gpu_fpga_scenario",
            "percent",
            12,
            6,
            6,
            4,
            [{"color": "red", "value": None}, {"color": "yellow", "value": 15}, {"color": "green", "value": 30}],
        ),
        stat_panel(
            p,
            "GPU Training Acceleration",
            "SELECT NOW() AS time, gpu_training_acceleration::NUMERIC AS value FROM gpu_fpga_scenario",
            "suffix:x",
            18,
            6,
            6,
            4,
        ),
        barchart_panel(
            p,
            "Training Latency",
            """
            SELECT platform AS "Platform", training_latency_ms AS "Training latency (ms)"
            FROM gpu_fpga_platform_metrics
            ORDER BY training_latency_ms DESC
            """,
            0,
            10,
            8,
            8,
        ),
        barchart_panel(
            p,
            "Inference Latency",
            """
            SELECT platform AS "Platform", inference_latency_ms AS "Inference latency (ms)"
            FROM gpu_fpga_platform_metrics
            ORDER BY inference_latency_ms DESC
            """,
            8,
            10,
            8,
            8,
        ),
        barchart_panel(
            p,
            "Performance per Watt",
            """
            SELECT platform AS "Platform", performance_per_watt AS "Performance per watt"
            FROM gpu_fpga_platform_metrics
            ORDER BY performance_per_watt DESC
            """,
            16,
            10,
            8,
            8,
        ),
        barchart_panel(
            p,
            "Speed-up Comparison",
            """
            SELECT metric, value
            FROM (
              SELECT 'GPU training speed-up' AS metric, speedup_training AS value
              FROM gpu_fpga_platform_metrics
              WHERE platform = 'GPU'
              UNION ALL
              SELECT 'FPGA training speed-up', speedup_training
              FROM gpu_fpga_platform_metrics
              WHERE platform = 'FPGA'
              UNION ALL
              SELECT 'GPU inference speed-up', speedup_inference
              FROM gpu_fpga_platform_metrics
              WHERE platform = 'GPU'
              UNION ALL
              SELECT 'FPGA inference speed-up', speedup_inference
              FROM gpu_fpga_platform_metrics
              WHERE platform = 'FPGA'
            ) speeds
            """,
            0,
            18,
            8,
            8,
        ),
        barchart_panel(
            p,
            "Before vs After Energy Consumption",
            """
            SELECT metric, value
            FROM (
              SELECT 'Baseline energy' AS metric, baseline_energy_j AS value FROM gpu_fpga_scenario
              UNION ALL
              SELECT 'Optimised energy', optimised_energy_j FROM gpu_fpga_scenario
            ) energy
            """,
            8,
            18,
            8,
            8,
        ),
        barchart_panel(
            p,
            "Before vs After CO2 Estimate",
            """
            SELECT metric, value
            FROM (
              SELECT 'Baseline CO2' AS metric, baseline_co2_kg AS value FROM gpu_fpga_scenario
              UNION ALL
              SELECT 'Optimised CO2', optimised_co2_kg FROM gpu_fpga_scenario
            ) carbon
            """,
            16,
            18,
            8,
            8,
        ),
        table_panel(
            p,
            "Platform Metrics",
            """
            SELECT
              platform AS "Platform",
              role_description AS "Role",
              training_latency_ms AS "Training latency ms",
              inference_latency_ms AS "Inference latency ms",
              speedup_training AS "Training speed-up",
              speedup_inference AS "Inference speed-up",
              performance_per_watt AS "Performance per watt"
            FROM gpu_fpga_platform_metrics
            ORDER BY CASE platform WHEN 'CPU' THEN 1 WHEN 'GPU' THEN 2 ELSE 3 END
            """,
            0,
            26,
            12,
            8,
        ),
        table_panel(
            p,
            "Fraud Detection Workload Demo",
            f"""
            SELECT step AS "Step", status AS "Status"
            FROM (
              SELECT 1 AS sort_order, 'Transactions received' AS step,
                CASE
                  WHEN {SCENARIO_PHASE_VAR} IN ('running', 'scheduler', 'gpu_training', 'fpga_inference', 'optimised') THEN 'complete'
                  ELSE 'active'
                END AS status
              UNION ALL
              SELECT 2, 'CPU baseline execution',
                CASE
                  WHEN {SCENARIO_PHASE_VAR} = 'baseline' THEN 'active'
                  WHEN {SCENARIO_PHASE_VAR} IN ('running', 'scheduler', 'gpu_training', 'fpga_inference', 'optimised') THEN 'complete'
                  ELSE 'pending'
                END
              UNION ALL
              SELECT 3, 'AI scheduler selects hardware',
                CASE
                  WHEN {SCENARIO_PHASE_VAR} = 'scheduler' THEN 'active'
                  WHEN {SCENARIO_PHASE_VAR} IN ('gpu_training', 'fpga_inference', 'optimised') THEN 'complete'
                  ELSE 'pending'
                END
              UNION ALL
              SELECT 4, 'GPU training starts',
                CASE
                  WHEN {SCENARIO_PHASE_VAR} = 'gpu_training' THEN 'active'
                  WHEN {SCENARIO_PHASE_VAR} IN ('fpga_inference', 'optimised') THEN 'complete'
                  ELSE 'pending'
                END
              UNION ALL
              SELECT 5, 'FPGA scoring starts',
                CASE
                  WHEN {SCENARIO_PHASE_VAR} = 'fpga_inference' THEN 'active'
                  WHEN {SCENARIO_PHASE_VAR} = 'optimised' THEN 'complete'
                  ELSE 'pending'
                END
              UNION ALL
              SELECT 6, 'Suspicious transactions flagged',
                CASE
                  WHEN {SCENARIO_PHASE_VAR} = 'optimised' THEN 'complete'
                  ELSE 'pending'
                END
              UNION ALL
              SELECT 7, 'Energy / performance improvement displayed',
                CASE
                  WHEN {SCENARIO_PHASE_VAR} = 'optimised' THEN 'complete'
                  ELSE 'pending'
                END
            ) flow
            ORDER BY sort_order
            """,
            12,
            26,
            12,
            8,
        ),
        text_panel(
            p,
            "Before / After Optimisation",
            dedent(
                f"""
                ### Before / After Optimisation

                **Before AI Optimisation**

                - CPU-only baseline
                - higher latency
                - higher energy per useful computation

                **After AI Optimisation**

                - GPU-assisted training
                - FPGA-assisted inference
                - lower latency
                - improved performance per watt
                - reduced energy consumption

                **Formula notes**

                - Energy = Power × Time
                - Improvement (%) = (Baseline Energy - Optimised Energy) / Baseline Energy × 100
                - Performance per Watt = Throughput / Power

                **Measured result**

                - Baseline energy: {scenario['baseline_energy_j']} J
                - Optimised energy: {scenario['optimised_energy_j']} J
                - Improvement: {scenario['energy_saving_percent']:.2f}%
                """
            ).strip(),
            0,
            34,
            12,
            7,
        ),
        text_panel(
            p,
            "Why GPU? Why FPGA?",
            dedent(
                """
                ### Why GPU? Why FPGA?

                - **GPU** is selected for parallel model-building because it reduces training latency relative to the CPU baseline.
                - **FPGA** is selected for low-latency fraud scoring because it delivers the strongest inference speed-up and the highest performance per watt.
                - **CPU** remains in the loop for data preparation and orchestration.
                """
            ).strip(),
            12,
            34,
            12,
            7,
        ),
    ]
    return dashboard_base(
        "GPU–FPGA Acceleration",
        "idt4-gpu-fpga",
        with_demo_nav(p, panels, "idt4-gpu-fpga"),
        time_from="now-6h",
        include_scope_filters=False,
        extra_variables=connection_context_variables(hidden=True) + [scenario_phase_variable()],
    )


def write_dashboard(filename, dashboard):
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    (DASHBOARD_DIR / filename).write_text(json.dumps(dashboard, indent=2) + "\n")


def main():
    write_dashboard("connect_data_centre.json", connect_data_centre_dashboard())
    write_dashboard("overview.json", overview_dashboard())
    write_dashboard("analytics.json", analytics_dashboard())
    write_dashboard("carbon.json", carbon_dashboard())
    write_dashboard("sustainability_kpis.json", sustainability_kpis_dashboard())
    write_dashboard("ai_optimisation.json", ai_optimisation_dashboard())
    write_dashboard("gpu_fpga_acceleration.json", gpu_fpga_acceleration_dashboard())


if __name__ == "__main__":
    main()
