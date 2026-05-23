from datetime import datetime, time
from html import escape
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# =========================
# 화면 설정
# =========================
st.set_page_config(
    page_title="컴프레셔 시뮬레이터",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================
# 화면 스타일
# =========================
st.markdown(
    """
<style>
    .stApp {
        background: #ffffff;
        color: #1f2933;
    }

    .block-container {
        padding-top: 30px;
        padding-bottom: 24px;
    }

    .main-title {
        font-size: 38px;
        font-weight: 800;
        margin-bottom: 4px;
        letter-spacing: 0;
    }

    .sub-title {
        color: #667085;
        font-size: 16px;
        margin-bottom: 12px;
    }

    .panel {
        background: #ffffff;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 14px;
        min-height: 100%;
    }

    .panel-title {
        color: #1f2933;
        font-size: 19px;
        font-weight: 800;
        margin-bottom: 8px;
    }

    .status-card {
        background: #ffffff;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 20px;
        min-height: 124px;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }

    .status-label {
        color: #667085;
        font-size: 19px;
        font-weight: 800;
        margin-bottom: 8px;
    }

    .status-value {
        font-size: 38px;
        font-weight: 800;
        color: #101828;
    }

    .status-unit {
        font-size: 17px;
        color: #667085;
        margin-left: 5px;
    }

    .summary-section {
        margin-top: 12px;
    }

    .summary-sensor-grid,
    .summary-info-grid {
        display: grid;
        gap: 12px;
        margin-bottom: 14px;
    }

    .summary-sensor-grid {
        grid-template-columns: repeat(3, minmax(220px, 1fr));
    }

    .summary-info-grid {
        grid-template-columns: repeat(4, minmax(190px, 1fr));
    }

    .summary-info-card {
        background: #ffffff;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 18px 20px;
        min-height: 112px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }

    .summary-info-label {
        color: #475467;
        font-size: 16px;
        font-weight: 800;
        margin-bottom: 10px;
    }

    .summary-info-value {
        color: #101828;
        font-size: 25px;
        font-weight: 800;
        line-height: 1.22;
        overflow-wrap: anywhere;
    }

    @media (max-width: 1180px) {
        .summary-sensor-grid,
        .summary-info-grid {
            grid-template-columns: repeat(2, minmax(220px, 1fr));
        }
    }

    @media (max-width: 720px) {
        .summary-sensor-grid,
        .summary-info-grid {
            grid-template-columns: 1fr;
        }
    }

    .badge {
        display: inline-block;
        padding: 8px 14px;
        border-radius: 999px;
        font-size: 18px;
        font-weight: 800;
        text-align: center;
    }

    .badge-running {
        background: rgba(38, 194, 129, 0.14);
        color: #39d98a;
        border: 1px solid #39d98a;
    }

    .badge-idle {
        background: rgba(245, 166, 35, 0.14);
        color: #f5b14c;
        border: 1px solid #f5b14c;
    }

    .badge-off {
        background: rgba(102, 112, 133, 0.12);
        color: #475467;
        border: 1px solid #98a2b3;
    }

    .state-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
    }

    .state-tile {
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 12px 10px;
        min-height: 88px;
        background: #f8fafc;
        opacity: 0.58;
    }

    .state-tile.active {
        opacity: 1;
        border-color: #39d98a;
        box-shadow: inset 0 0 0 1px rgba(57, 217, 138, 0.35);
    }

    .state-name {
        color: #1f2933;
        font-size: 17px;
        font-weight: 800;
        margin-bottom: 6px;
    }

    .state-copy {
        color: #667085;
        font-size: 13px;
        line-height: 1.35;
    }

    .alert-panel {
        background: #ffffff;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 18px 20px;
        margin-top: 2px;
        margin-bottom: 14px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }

    .alert-title {
        color: #1f2933;
        font-size: 27px;
        font-weight: 800;
        margin-bottom: 7px;
    }

    .alert-copy {
        color: #667085;
        font-size: 17px;
        line-height: 1.4;
    }

    .alert-danger {
        border-color: #ff605c;
        background: rgba(255, 96, 92, 0.12);
        box-shadow: inset 0 0 0 2px rgba(255, 96, 92, 0.48);
    }

    .alert-normal {
        border-color: #39d98a;
        box-shadow: inset 0 0 0 1px rgba(57, 217, 138, 0.22);
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 16px;
        min-height: 92px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }

    div[data-testid="stMetric"] * {
        color: #101828 !important;
    }

    div[data-testid="stSlider"] {
        padding-top: 2px;
        padding-bottom: 2px;
    }

    div[data-testid="stSlider"] label p {
        font-size: 15px;
        font-weight: 800;
    }

    div[data-testid="stMetricLabel"] p {
        font-size: 18px;
        font-weight: 800;
        color: #475467 !important;
    }

    div[data-testid="stMetricValue"] {
        font-size: 30px;
        font-weight: 800;
        color: #101828 !important;
    }

    div[data-testid="stMetricValue"] * {
        color: #101828 !important;
    }

    div[data-testid="stMetricDelta"] * {
        color: #667085 !important;
    }

    div[data-testid="stWidgetLabel"],
    div[data-testid="stWidgetLabel"] *,
    div[data-testid="stTextInput"] label,
    div[data-testid="stTextInput"] label *,
    div[data-testid="stTimeInput"] label,
    div[data-testid="stTimeInput"] label *,
    div[data-testid="stSlider"] label,
    div[data-testid="stSlider"] label *,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stSelectbox"] label * {
        color: #475467 !important;
        font-weight: 800 !important;
    }

    div[data-testid="stTextInput"] input,
    div[data-testid="stTimeInput"] input,
    div[data-testid="stNumberInput"] input {
        background-color: #ffffff !important;
        color: #101828 !important;
        border-color: #cfd6e2 !important;
        caret-color: #101828 !important;
    }

    div[data-testid="stTextInput"] input::placeholder,
    div[data-testid="stTimeInput"] input::placeholder {
        color: #667085 !important;
        opacity: 1 !important;
    }

    div[data-testid="stTimeInput"] div[data-baseweb="select"] > div,
    div[data-testid="stTimeInput"] div[data-baseweb="input"] > div {
        background-color: #ffffff !important;
        border-color: #cfd6e2 !important;
        color: #101828 !important;
    }

    div[data-testid="stTimeInput"] div[data-baseweb="select"] *,
    div[data-testid="stTimeInput"] div[data-baseweb="input"] * {
        color: #101828 !important;
    }

    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        min-height: 42px;
        background-color: #ffffff !important;
        border-color: #cfd6e2 !important;
        color: #101828 !important;
    }

    div[data-testid="stSelectbox"] div[data-baseweb="select"] * {
        color: #101828 !important;
    }

    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border-color: #cfd6e2 !important;
    }

    div[data-baseweb="select"] svg {
        fill: #344054 !important;
    }

    div[data-baseweb="input"] > div {
        background-color: #ffffff !important;
        border-color: #cfd6e2 !important;
    }

    div[data-baseweb="input"] input {
        color: #101828 !important;
    }

    div[data-testid="stSlider"] label p {
        color: #475467 !important;
    }

    div[data-testid="stSlider"] [data-testid="stMarkdownContainer"] p {
        color: #475467 !important;
    }

    div[data-testid="stSlider"] [role="slider"] {
        color: #ff4b4b !important;
    }

    .control-label {
        color: #475467;
        font-size: 14px;
        font-weight: 800;
        margin-bottom: 6px;
    }

    div[data-testid="stButton"] button:not([data-testid="stBaseButton-primary"]),
    button[data-testid="stBaseButton-secondary"] {
        min-height: 42px;
        background-color: #ffffff !important;
        border: 1px solid #cfd6e2 !important;
        color: #101828 !important;
        font-weight: 800;
        border-radius: 8px;
    }

    div[data-testid="stButton"] button:not([data-testid="stBaseButton-primary"]) *,
    button[data-testid="stBaseButton-secondary"] * {
        color: #101828 !important;
    }

    div[data-testid="stButton"] button:not([data-testid="stBaseButton-primary"]):hover,
    button[data-testid="stBaseButton-secondary"]:hover {
        border-color: #ff6b5f !important;
        color: #e5483f !important;
        background-color: #fff4f2 !important;
    }

    div[data-testid="stButton"] button:not([data-testid="stBaseButton-primary"]):hover *,
    button[data-testid="stBaseButton-secondary"]:hover * {
        color: #e5483f !important;
    }

    div[data-testid="stButton"] button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-primary"] {
        min-height: 42px;
        background-color: #ff6b5f !important;
        border: 1px solid #ff6b5f !important;
        color: #ffffff !important;
        font-weight: 800;
        border-radius: 8px;
        box-shadow: 0 1px 2px rgba(255, 107, 95, 0.22);
    }

    button[data-testid="stBaseButton-primary"] * {
        color: #ffffff !important;
    }

    div[data-testid="stButton"] button[data-testid="stBaseButton-primary"]:hover,
    button[data-testid="stBaseButton-primary"]:hover {
        background-color: #e5483f !important;
        border-color: #e5483f !important;
        color: #ffffff !important;
    }

    .js-plotly-plot text {
        fill: #1f2933 !important;
        color: #1f2933 !important;
    }

    div[data-testid="stSegmentedControl"] button {
        min-height: 42px;
        background-color: #ffffff;
        border-color: #cfd6e2;
        color: #344054 !important;
        font-weight: 800;
    }

    div[data-testid="stSegmentedControl"] button * {
        color: #344054 !important;
    }

    div[data-testid="stSegmentedControl"] label {
        min-height: 42px;
        background-color: #ffffff !important;
        border-color: #cfd6e2 !important;
        color: #344054 !important;
        font-weight: 800;
    }

    div[data-testid="stSegmentedControl"] label * {
        color: #344054 !important;
    }

    div[data-testid="stSegmentedControl"] button[aria-pressed="true"] {
        background-color: #fff4f2;
        border-color: #ff6b5f;
        color: #e5483f !important;
    }

    div[data-testid="stSegmentedControl"] button[aria-selected="true"] {
        background-color: #fff4f2;
        border-color: #ff6b5f;
        color: #e5483f !important;
    }

    div[data-testid="stSegmentedControl"] button[aria-pressed="true"] * {
        color: #e5483f !important;
    }

    div[data-testid="stSegmentedControl"] button[aria-selected="true"] * {
        color: #e5483f !important;
    }

    div[data-testid="stSegmentedControl"] label:has(input:checked) {
        background-color: #fff4f2 !important;
        border-color: #ff6b5f !important;
        color: #e5483f !important;
    }

    div[data-testid="stSegmentedControl"] label:has(input:checked) * {
        color: #e5483f !important;
    }

    div[data-testid="stCaptionContainer"] {
        font-size: 14px;
        color: #667085;
    }

    div[data-testid="stCaptionContainer"] * {
        color: #667085 !important;
    }

    .log-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        overflow: hidden;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }

    .log-table th {
        background: #f8fafc;
        color: #475467;
        font-size: 14px;
        font-weight: 800;
        text-align: left;
        padding: 11px 12px;
        border-bottom: 1px solid #d8dee8;
    }

    .log-table td {
        color: #101828;
        font-size: 14px;
        font-weight: 700;
        padding: 12px;
        border-bottom: 1px solid #edf1f7;
        vertical-align: middle;
    }

    .log-table tr:last-child td {
        border-bottom: 0;
    }

    .log-table .priority-high {
        color: #d92d20;
    }

    .log-table .priority-medium {
        color: #b54708;
    }

    .log-table .priority-low {
        color: #475467;
    }

    .empty-log {
        padding: 16px;
        border: 1px solid #b9dcff;
        border-radius: 8px;
        background: #eef7ff;
        color: #1570ef;
        font-size: 15px;
        font-weight: 700;
    }

    div[data-testid="stVerticalBlock"] {
        gap: 0.7rem;
    }

    div[data-testid="stHorizontalBlock"] {
        gap: 0.9rem;
    }

    #MainMenu, header, footer {
        visibility: hidden;
    }
</style>
""",
    unsafe_allow_html=True,
)


STATUS_META = {
    "running": {
        "label": "가동 중",
        "badge_class": "badge-running",
        "copy": "부하가 걸려 압축 공기를 생산하고 있습니다.",
    },
    "idle": {
        "label": "유휴 상태",
        "badge_class": "badge-idle",
        "copy": "전원은 켜져 있지만 부하가 낮아 대기하고 있습니다.",
    },
    "off": {
        "label": "비가동 상태",
        "badge_class": "badge-off",
        "copy": "컴프레셔가 정지되어 출력이 없습니다.",
    },
}

LEAK_ACTIVE_LEVEL = 70
STATIC_CHART_CONFIG = {
    "displayModeBar": False,
    "staticPlot": True,
}


def format_time_mode(time_mode):
    return "미사용 시간대" if time_mode == "non_production" else "사용 시간대"


def format_time_mode_reason(reason, time_mode):
    reason_labels = {
        "working_hours": "사용 시간대",
        "off_hours": "미사용 시간대",
        "lunch_break": "점심시간",
        "rest_break": "쉬는시간",
    }
    return reason_labels.get(reason, format_time_mode(time_mode))


def parse_config_time(value, fallback):
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def format_usage_period(config):
    return f'{config["usage_start_time"]} ~ {config["usage_end_time"]}'


def format_lunch_period(config):
    return f'{config["lunch_start_time"]} ~ {config["lunch_end_time"]}'


def format_rest_period(config):
    return f'{config["rest_start_time"]} ~ {config["rest_end_time"]}'


def init_state():
    if "compressor_on" not in st.session_state:
        st.session_state.compressor_on = True
    if "api_base_url" not in st.session_state:
        st.session_state.api_base_url = "http://localhost:8000"
    if "selected_equipment_id" not in st.session_state:
        st.session_state.selected_equipment_id = ""


def api_request(method, path, payload=None, timeout=2.5, params=None):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    url = f"{st.session_state.api_base_url}{path}"
    if params:
        clean_params = {key: value for key, value in params.items() if value}
        if clean_params:
            url = f"{url}?{urlencode(clean_params)}"

    request = Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        st.session_state.api_error = str(exc)
        return None


def selected_equipment_params():
    return {"equipment_id": st.session_state.selected_equipment_id}


def fetch_equipment():
    return api_request("GET", "/equipment")


def create_equipment(name, area):
    return api_request("POST", "/equipment", {"name": name, "area": area})


def fetch_snapshot():
    st.session_state.api_error = ""
    return api_request("GET", "/simulator/status", params=selected_equipment_params())


def update_server_config(config):
    return api_request("PUT", "/simulator/config", config, params=selected_equipment_params())


def set_session_value(key, value):
    st.session_state[key] = value


def button_choice(label, options, current, key_prefix, state_key=None, value_map=None):
    st.markdown(f'<div class="control-label">{escape(label)}</div>', unsafe_allow_html=True)
    columns = st.columns(len(options))
    selected = current
    for column, option in zip(columns, options):
        with column:
            button_kwargs = {}
            if state_key:
                button_kwargs["on_click"] = set_session_value
                button_kwargs["args"] = (state_key, value_map.get(option, option) if value_map else option)
            clicked = st.button(
                option,
                key=f"{key_prefix}_{option}",
                type="primary" if option == current else "secondary",
                width="stretch",
                **button_kwargs,
            )
            if clicked:
                selected = option
    return selected


def line_chart(df, y, title, unit, color, height=245):
    if df.empty or "time" not in df or y not in df:
        df = pd.DataFrame({"time": [0], y: [0]})

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["time"],
            y=df[y],
            mode="lines",
            name=title,
            line=dict(width=2.4, color=color),
            fill="tozeroy",
            fillcolor=color.replace("1)", "0.16)") if color.startswith("rgba") else None,
        )
    )

    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=22, r=18, t=38, b=26),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color="#1f2933", size=13),
        title=dict(text=title, font=dict(size=16, color="#101828")),
        xaxis=dict(
            gridcolor="#d8dee8",
            zerolinecolor="#d8dee8",
            linecolor="#d8dee8",
            tickfont=dict(size=12, color="#475467"),
        ),
        yaxis=dict(
            gridcolor="#d8dee8",
            zerolinecolor="#d8dee8",
            linecolor="#d8dee8",
            tickfont=dict(size=12, color="#475467"),
        ),
        showlegend=False,
        hovermode=False,
        dragmode=False,
    )
    return fig


def chart_title(latest, key, title, unit, precision=1):
    value = float(latest.get(key, 0))
    return f"{title}: {value:.{precision}f} {unit}"


def render_alert_log(alerts):
    if not alerts:
        st.markdown(
            '<div class="empty-log">아직 기록된 누설 또는 유휴 전력 낭비 알림이 없습니다.</div>',
            unsafe_allow_html=True,
        )
        return

    headers = ["발생 시간", "알림 유형", "우선순위", "점검 위치", "내용"]
    key_map = ["timestamp", "type", "priority", "location", "message"]
    priority_classes = {
        "높음": "priority-high",
        "중간": "priority-medium",
        "낮음": "priority-low",
    }
    header_html = "".join(f"<th>{header}</th>" for header in headers)
    rows = []
    for alert in alerts:
        cells = []
        for key in key_map:
            value = escape(str(alert.get(key, "")))
            css_class = priority_classes.get(alert.get("priority"), "") if key == "priority" else ""
            class_attr = f' class="{css_class}"' if css_class else ""
            cells.append(f"<td{class_attr}>{value}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    st.markdown(
        f"""
        <table class="log-table">
            <thead><tr>{header_html}</tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )


def metric_card_html(label, value, unit):
    return (
        '<div class="status-card">'
        f'<div class="status-label">{escape(str(label))}</div>'
        "<div>"
        f'<span class="status-value">{escape(str(value))}</span>'
        f'<span class="status-unit">{escape(str(unit))}</span>'
        "</div>"
        "</div>"
    )


def metric_card(label, value, unit):
    st.markdown(
        metric_card_html(label, value, unit),
        unsafe_allow_html=True,
    )


def summary_info_card_html(label, value):
    return (
        '<div class="summary-info-card">'
        f'<div class="summary-info-label">{escape(str(label))}</div>'
        f'<div class="summary-info-value">{escape(str(value))}</div>'
        "</div>"
    )


def state_panel(active_state):
    tiles = []
    for key in ("running", "idle", "off"):
        active = " active" if key == active_state else ""
        meta = STATUS_META[key]
        tiles.append(
            (
                f'<div class="state-tile{active}">'
                f'<div class="state-name">{meta["label"]}</div>'
                f'<div class="state-copy">{meta["copy"]}</div>'
                "</div>"
            )
        )
    st.markdown(
        (
            '<div class="panel">'
            '<div class="panel-title">운전 상태 구분</div>'
            f'<div class="state-grid">{"".join(tiles)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


init_state()
equipment_response = fetch_equipment()
equipment_list = equipment_response["equipment"] if equipment_response else []
equipment_ids = {equipment["id"] for equipment in equipment_list}
if equipment_response and st.session_state.selected_equipment_id not in equipment_ids:
    st.session_state.selected_equipment_id = equipment_response["default_equipment_id"]
snapshot = fetch_snapshot()
server_available = snapshot is not None
selected_equipment = snapshot.get("equipment", {}) if server_available else {}

default_config = {
    "time_mode": "production",
    "usage_start_time": "08:00",
    "usage_end_time": "18:00",
    "lunch_start_time": "12:00",
    "lunch_end_time": "13:00",
    "rest_start_time": "15:00",
    "rest_end_time": "15:15",
    "load_percent": 68,
    "leak_level": 0,
    "idle_power_level": 0,
    "vibration_base": 0.014,
    "current_base": 2.2,
    "pressure_target": 4.2,
    "temperature_base": 29.0,
    "air_frequency": 412,
}
config = {**default_config, **snapshot["config"]} if server_available else default_config
current_power = snapshot["compressor_on"] if server_available else st.session_state.compressor_on
if server_available and not current_power:
    powered_snapshot = api_request("POST", "/simulator/power", {"compressor_on": True}, params=selected_equipment_params())
    if powered_snapshot is not None:
        snapshot = powered_snapshot
        selected_equipment = snapshot.get("equipment", selected_equipment)
        config = {**default_config, **snapshot["config"]}
        current_power = True
st.session_state.compressor_on = current_power
if "leak_scenario" not in st.session_state:
    st.session_state.leak_scenario = "leak" if int(config["leak_level"]) > 0 else "normal"
if "page_control" not in st.session_state:
    st.session_state.page_control = "요약"
if st.session_state.page_control == "대시보드":
    st.session_state.page_control = "요약"

# =========================
# 머리글
# =========================
equipment_name = selected_equipment.get("name", "설비 연결 대기")
equipment_area = selected_equipment.get("area", "구역 미지정")
st.markdown(
    f"""
    <div class="main-title">{equipment_name} · {equipment_area}</div>
    <div class="sub-title">압축공기 누설 및 유휴설비 절전 알림 시스템</div>
    """,
    unsafe_allow_html=True,
)

control_spacer, equipment_col, page_col = st.columns([1.7, 0.85, 0.85])

with equipment_col:
    if equipment_list:
        equipment_labels = {
            f'{equipment["name"]} · {equipment["area"]}': equipment["id"]
            for equipment in equipment_list
        }
        selected_label = next(
            (
                label
                for label, equipment_id in equipment_labels.items()
                if equipment_id == st.session_state.selected_equipment_id
            ),
            next(iter(equipment_labels)),
        )
        selected_equipment_label = st.selectbox(
            "설비",
            list(equipment_labels.keys()),
            index=list(equipment_labels.keys()).index(selected_label),
            label_visibility="collapsed",
            key="equipment_select_control",
        )
        selected_equipment_id = equipment_labels[selected_equipment_label]
        if selected_equipment_id != st.session_state.selected_equipment_id:
            st.session_state.selected_equipment_id = selected_equipment_id
            st.rerun()

with page_col:
    selected_page = button_choice(
        "페이지",
        ["요약", "그래프", "설정"],
        st.session_state.page_control,
        "page_control",
    )
    if selected_page != st.session_state.page_control:
        st.session_state.page_control = selected_page
        st.rerun()

if not server_available:
    st.error(f"서버 연결 실패: {st.session_state.get('api_error', '응답 없음')}")
    st.info("먼저 터미널에서 `uv run uvicorn main:app --reload --port 8000` 서버를 실행해주세요.")

def build_live_values():
    live_snapshot = fetch_snapshot()
    active_state = live_snapshot["status"] if live_snapshot else "off"
    history = live_snapshot["history"] if live_snapshot else []
    alerts = live_snapshot["alerts"] if live_snapshot else []
    df = pd.DataFrame(history)
    latest = live_snapshot["latest"] if live_snapshot else {
        "time_mode": "production",
        "time_mode_reason": "working_hours",
        "usage_start_time": "08:00",
        "usage_end_time": "18:00",
        "lunch_start_time": "12:00",
        "lunch_end_time": "13:00",
        "rest_start_time": "15:00",
        "rest_end_time": "15:15",
        "vibration": 0,
        "current": 0,
        "pressure": 0,
        "temperature": 0,
        "frequency": 0,
        "air_flow": 0,
        "sound_db": 0,
        "operation": 0,
        "alarm_level": 0,
        "leak_alert": False,
        "idle_power_alert": False,
        "alert_level": 0,
        "anomaly_score": 0,
        "leak_score": 0,
        "idle_power_score": 0,
        "baseline_ready": False,
        "baseline_count": 0,
        "baseline_source": "dynamic",
        "baseline_air_flow": 0,
        "baseline_sound_db": 0,
        "baseline_air_flow_limit": 0,
        "baseline_sound_db_limit": 0,
        "leak_sustain_count": 0,
        "idle_power_sustain_count": 0,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    latest = {
        "time_mode": "production",
        "time_mode_reason": "working_hours",
        "usage_start_time": "08:00",
        "usage_end_time": "18:00",
        "lunch_start_time": "12:00",
        "lunch_end_time": "13:00",
        "rest_start_time": "15:00",
        "rest_end_time": "15:15",
        "vibration": 0,
        "current": 0,
        "pressure": 0,
        "temperature": 0,
        "frequency": 0,
        "air_flow": 0,
        "sound_db": 0,
        "operation": 0,
        "alarm_level": 0,
        "leak_alert": False,
        "idle_power_alert": False,
        "alert_level": 0,
        "anomaly_score": 0,
        "leak_score": 0,
        "idle_power_score": 0,
        "baseline_ready": False,
        "baseline_count": 0,
        "baseline_source": "dynamic",
        "baseline_air_flow": 0,
        "baseline_sound_db": 0,
        "baseline_air_flow_limit": 0,
        "baseline_sound_db_limit": 0,
        "leak_sustain_count": 0,
        "idle_power_sustain_count": 0,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        **latest,
    }
    return active_state, df, latest, alerts


def render_settings_page():
    global snapshot

    control_col, state_col = st.columns([1.35, 1])

    with control_col:
        st.markdown('<div class="panel-title">설비 등록</div>', unsafe_allow_html=True)
        e1, e2, e3 = st.columns([1, 1, 0.58])
        with e1:
            new_equipment_name = st.text_input("이름", placeholder="예: 컴프레셔 2")
        with e2:
            new_equipment_area = st.text_input("구역", placeholder="예: B동 2층")
        with e3:
            st.write("")
            register_clicked = st.button("등록", width="stretch")
        if register_clicked:
            name = new_equipment_name.strip()
            area = new_equipment_area.strip()
            if not name or not area:
                st.warning("설비 이름과 구역을 모두 입력해주세요.")
            else:
                created = create_equipment(name, area)
                if created is not None:
                    st.session_state.selected_equipment_id = created["equipment"]["id"]
                    st.rerun()

        st.markdown('<div class="panel-title">운전 조작</div>', unsafe_allow_html=True)
        t1, t2 = st.columns(2)
        with t1:
            usage_start_time = st.time_input(
                "컴프레셔 사용 시작",
                value=parse_config_time(config["usage_start_time"], time(8, 0)),
                step=900,
            )
        with t2:
            usage_end_time = st.time_input(
                "컴프레셔 사용 종료",
                value=parse_config_time(config["usage_end_time"], time(18, 0)),
                step=900,
            )

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            lunch_start_time = st.time_input(
                "점심 시작",
                value=parse_config_time(config["lunch_start_time"], time(12, 0)),
                step=900,
            )
        with b2:
            lunch_end_time = st.time_input(
                "점심 종료",
                value=parse_config_time(config["lunch_end_time"], time(13, 0)),
                step=900,
            )
        with b3:
            rest_start_time = st.time_input(
                "쉬는시간 시작",
                value=parse_config_time(config["rest_start_time"], time(15, 0)),
                step=900,
            )
        with b4:
            rest_end_time = st.time_input(
                "쉬는시간 종료",
                value=parse_config_time(config["rest_end_time"], time(15, 15)),
                step=900,
            )

        c1, c2, c3 = st.columns(3)
        with c1:
            load_percent = st.slider("부하율 (%)", 0, 100, int(config["load_percent"]), 1)
            current_leak_label = "누설 발생" if st.session_state.leak_scenario == "leak" else "누설 없음"
            leak_scenario_label = button_choice(
                "누설 상황",
                ["누설 없음", "누설 발생"],
                current_leak_label,
                "leak_scenario_control",
                state_key="leak_scenario",
                value_map={"누설 없음": "normal", "누설 발생": "leak"},
            )
            leak_scenario = "leak" if leak_scenario_label == "누설 발생" else "normal"
            st.session_state.leak_scenario = leak_scenario
            leak_level = LEAK_ACTIVE_LEVEL if leak_scenario == "leak" else 0
            vibration_base = st.slider("진동 기준값 (g RMS)", 0.001, 0.050, float(config["vibration_base"]), 0.001)
        with c2:
            idle_power_level = st.slider("유휴 전력 정도 (%)", 0, 100, int(config["idle_power_level"]), 1)
            current_base = st.slider("전류 기준값 (A)", 0.2, 8.0, float(config["current_base"]), 0.1)
            pressure_target = st.slider("목표 압력 (bar)", 0.2, 10.0, float(config["pressure_target"]), 0.1)
        with c3:
            temperature_base = st.slider("기준 온도 (℃)", 10.0, 60.0, float(config["temperature_base"]), 0.5)
            air_frequency = st.slider("공기 주파수 (Hz)", 0, 500, int(config["air_frequency"]), 1)

    config_payload = {
        "usage_start_time": usage_start_time.strftime("%H:%M"),
        "usage_end_time": usage_end_time.strftime("%H:%M"),
        "lunch_start_time": lunch_start_time.strftime("%H:%M"),
        "lunch_end_time": lunch_end_time.strftime("%H:%M"),
        "rest_start_time": rest_start_time.strftime("%H:%M"),
        "rest_end_time": rest_end_time.strftime("%H:%M"),
        "load_percent": load_percent,
        "leak_level": leak_level,
        "idle_power_level": idle_power_level,
        "vibration_base": vibration_base,
        "current_base": current_base,
        "pressure_target": pressure_target,
        "temperature_base": temperature_base,
        "air_frequency": air_frequency,
    }
    if server_available:
        updated_snapshot = update_server_config(config_payload)
        if updated_snapshot is not None:
            snapshot = updated_snapshot

    with state_col:
        active_state = snapshot["status"] if server_available else "off"
        state_panel(active_state)

    with st.expander("현재 설정값", expanded=False):
        st.dataframe(
            pd.DataFrame(
                [
                    {"항목": "컴프레셔 사용 시간대", "값": format_usage_period(config_payload)},
                    {"항목": "점심시간", "값": format_lunch_period(config_payload)},
                    {"항목": "쉬는시간", "값": format_rest_period(config_payload)},
                    {"항목": "부하율", "값": f'{config_payload["load_percent"]}%'},
                    {"항목": "누설 상황", "값": "누설 발생" if config_payload["leak_level"] > 0 else "누설 없음"},
                    {"항목": "유휴 전력 정도", "값": f'{config_payload["idle_power_level"]}%'},
                    {"항목": "진동 기준값", "값": f'{config_payload["vibration_base"]:.3f} g RMS'},
                    {"항목": "전류 기준값", "값": f'{config_payload["current_base"]:.1f} A'},
                    {"항목": "목표 압력", "값": f'{config_payload["pressure_target"]:.1f} bar'},
                    {"항목": "기준 온도", "값": f'{config_payload["temperature_base"]:.1f} ℃'},
                    {"항목": "공기 주파수", "값": f'{config_payload["air_frequency"]} Hz'},
                ]
            ),
            width="stretch",
            hide_index=True,
        )


def render_status_badge():
    active_state, _, _, _ = build_live_values()
    status_meta = STATUS_META[active_state]
    st.markdown(
        f"""
        <div style="text-align:right; padding-top:10px;">
            <span class="badge {status_meta["badge_class"]}">{status_meta["label"]}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_state_panel():
    active_state, _, _, _ = build_live_values()
    state_panel(active_state)


def render_summary_body():
    active_state, df, latest, alerts = build_live_values()
    st.session_state.compressor_on = active_state != "off"

    is_non_production = latest.get("time_mode") == "non_production"
    leak_score = int(latest.get("leak_score", 0))
    idle_power_score = int(latest.get("idle_power_score", 0))
    anomaly_score = int(latest.get("anomaly_score", 0))
    baseline_ready = bool(latest.get("baseline_ready"))
    baseline_count = int(latest.get("baseline_count", 0))
    leak_sustain_count = int(latest.get("leak_sustain_count", 0))
    idle_power_sustain_count = int(latest.get("idle_power_sustain_count", 0))
    leak_text = (
        "누설 의심"
        if latest.get("leak_alert")
        else f"감지 중 {leak_sustain_count}/4"
        if is_non_production and leak_sustain_count > 0
        else f"참고 {leak_score}%"
        if not is_non_production and baseline_ready
        else f"기준 학습 중 {baseline_count}/20"
        if not baseline_ready
        else "정상"
    )
    idle_text = (
        "낭비 의심"
        if latest.get("idle_power_alert")
        else f"감지 중 {idle_power_sustain_count}/4"
        if is_non_production and idle_power_sustain_count > 0
        else "정상"
    )
    mode_text = format_time_mode_reason(latest.get("time_mode_reason"), latest.get("time_mode"))
    usage_period_text = f'{latest.get("usage_start_time", config["usage_start_time"])} ~ {latest.get("usage_end_time", config["usage_end_time"])}'
    baseline_text = "동적 기준선" if baseline_ready else f"기준 학습 중 {baseline_count}/20"
    alarm_count = int(df["alarm_level"].iloc[-80:].sum()) if "alarm_level" in df else 0
    alarm_text = "점검 필요" if alarm_count > 0 else "정상"
    operation_text = f'{latest["operation"]:.1f}%'

    has_confirmed_alert = latest.get("alert_level", 0) > 0
    has_anomaly_pattern = anomaly_score >= 100
    alert_class = "alert-danger" if has_confirmed_alert or has_anomaly_pattern else "alert-normal"
    if has_confirmed_alert:
        alert_title = "점검 알림 발생"
        alert_copy = "미사용 시간대에 동적 기준선을 벗어난 상태가 4회 연속 지속되었습니다. 알림 이력을 확인하고 우선 점검 위치를 확인하세요."
    elif has_anomaly_pattern:
        alert_title = "이상 패턴 감지 중"
        alert_copy = f"종합 의심도가 {anomaly_score}%입니다. 누설은 {leak_score}%, 유휴전력은 {idle_power_score}%이며 미사용 시간대에서 4회 연속 기준선을 벗어나면 점검 알림으로 확정됩니다."
    elif not baseline_ready:
        alert_title = "동적 기준선 학습 중"
        alert_copy = f"미사용 시간대 정상 패턴을 {baseline_count}/20개 수집했습니다. 기준선이 준비되면 누설 의심도를 계산합니다."
    else:
        alert_title = "현재 감지 상태 정상"
        alert_copy = f"{baseline_text}에서 지속적인 이상 패턴이 감지되지 않았습니다."
    st.markdown(
        (
            f'<div class="alert-panel {alert_class}">'
            f'<div class="alert-title">{alert_title}</div>'
            f'<div class="alert-copy">{alert_copy}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    sensor_cards = [
        ("공기 사용량", f'{latest["air_flow"]:.1f}', "L/min"),
        ("소음", f'{latest["sound_db"]:.1f}', "dB"),
        ("전류", f'{latest["current"]:.2f}', "A"),
        ("압력", f'{latest["pressure"]:.2f}', "bar"),
        ("온도", f'{latest["temperature"]:.1f}', "℃"),
        ("진동", f'{latest["vibration"]:.3f}', "g RMS"),
    ]
    st.markdown(
        (
            '<div class="summary-section">'
            '<div class="summary-sensor-grid">'
            + "".join(metric_card_html(label, value, unit) for label, value, unit in sensor_cards)
            + "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    info_cards = [
        ("시간 판정", mode_text),
        ("부하율", operation_text),
        ("누설", leak_text),
        ("유휴전력", idle_text),
        ("누설 의심도", f"{leak_score}%"),
        ("유휴 의심도", f"{idle_power_score}%"),
        ("사용 시간", usage_period_text),
        ("종합 의심도", f"{anomaly_score}%"),
    ]
    st.markdown(
        (
            '<div class="summary-info-grid">'
            + "".join(summary_info_card_html(label, value) for label, value in info_cards)
            + "</div>"
        ),
        unsafe_allow_html=True,
    )

    st.markdown(f'<div class="panel-title">알림 및 점검 이력 · {alarm_text}</div>', unsafe_allow_html=True)
    render_alert_log(alerts)

    server_time = latest.get("timestamp", datetime.now().strftime("%H:%M:%S"))
    st.caption(f"마지막 수신 시간: {server_time}")


def render_graph_body():
    active_state, df, latest, _ = build_live_values()
    st.session_state.compressor_on = active_state != "off"

    chart_items = [
        ("air_flow", "공기 사용량", "L/min", "rgba(57, 217, 138, 1)", 1),
        ("sound_db", "소음", "dB", "rgba(245, 166, 35, 1)", 1),
        ("current", "전류", "A", "rgba(68, 138, 255, 1)", 2),
        ("pressure", "압력", "bar", "rgba(255, 96, 92, 1)", 2),
        ("temperature", "온도", "℃", "rgba(150, 120, 255, 1)", 1),
        ("vibration", "진동", "g RMS", "rgba(94, 214, 214, 1)", 3),
    ]
    for row_start in range(0, len(chart_items), 3):
        columns = st.columns(3)
        for column, (key, label, unit, color, precision) in zip(columns, chart_items[row_start : row_start + 3]):
            with column:
                st.plotly_chart(
                    line_chart(
                        df,
                        key,
                        chart_title(latest, key, label, unit, precision=precision),
                        unit,
                        color,
                        height=275,
                    ),
                    width="stretch",
                    config=STATIC_CHART_CONFIG,
                    theme=None,
                )

    server_time = latest.get("timestamp", datetime.now().strftime("%H:%M:%S"))
    st.caption(f"마지막 수신 시간: {server_time}")


@st.fragment(run_every="1s")
def render_live_summary():
    render_summary_body()


@st.fragment(run_every="1s")
def render_live_graph():
    render_graph_body()


if selected_page == "설정":
    render_settings_page()
elif selected_page == "그래프":
    render_live_graph()
else:
    render_live_summary()
