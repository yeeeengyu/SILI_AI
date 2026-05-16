from datetime import datetime
import json
from urllib.error import HTTPError, URLError
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
        background: #101820;
        color: #f5f7fb;
    }

    .block-container {
        padding-top: 30px;
        padding-bottom: 42px;
    }

    .main-title {
        font-size: 42px;
        font-weight: 800;
        margin-bottom: 8px;
        letter-spacing: 0;
    }

    .sub-title {
        color: #a8b4c2;
        font-size: 20px;
        margin-bottom: 26px;
    }

    .panel {
        background: #17212b;
        border: 1px solid #2b3d4f;
        border-radius: 8px;
        padding: 22px;
        min-height: 100%;
    }

    .panel-title {
        color: #e8edf2;
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 14px;
    }

    .status-card {
        background: #17212b;
        border: 1px solid #2b3d4f;
        border-radius: 8px;
        padding: 22px;
        height: 136px;
    }

    .status-label {
        color: #a8b4c2;
        font-size: 21px;
        margin-bottom: 10px;
    }

    .status-value {
        font-size: 42px;
        font-weight: 800;
    }

    .status-unit {
        font-size: 18px;
        color: #a8b4c2;
        margin-left: 6px;
    }

    .badge {
        display: inline-block;
        padding: 10px 18px;
        border-radius: 999px;
        font-size: 22px;
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
        background: rgba(152, 164, 179, 0.14);
        color: #c5ced8;
        border: 1px solid #7e8b99;
    }

    .state-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
    }

    .state-tile {
        border: 1px solid #2b3d4f;
        border-radius: 8px;
        padding: 18px 14px;
        min-height: 128px;
        background: #121b24;
        opacity: 0.58;
    }

    .state-tile.active {
        opacity: 1;
        border-color: #39d98a;
        box-shadow: inset 0 0 0 1px rgba(57, 217, 138, 0.35);
    }

    .state-name {
        color: #f5f7fb;
        font-size: 22px;
        font-weight: 800;
        margin-bottom: 10px;
    }

    .state-copy {
        color: #a8b4c2;
        font-size: 17px;
        line-height: 1.5;
    }

    .alert-panel {
        background: #17212b;
        border: 1px solid #2b3d4f;
        border-radius: 8px;
        padding: 18px 20px;
        margin-top: 10px;
        margin-bottom: 18px;
    }

    .alert-title {
        color: #f5f7fb;
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 10px;
    }

    .alert-copy {
        color: #a8b4c2;
        font-size: 18px;
        line-height: 1.5;
    }

    .alert-danger {
        border-color: #ff605c;
        box-shadow: inset 0 0 0 1px rgba(255, 96, 92, 0.32);
    }

    .alert-normal {
        border-color: #39d98a;
        box-shadow: inset 0 0 0 1px rgba(57, 217, 138, 0.25);
    }

    div[data-testid="stMetric"] {
        background: #17212b;
        border: 1px solid #2b3d4f;
        border-radius: 8px;
        padding: 20px;
    }

    div[data-testid="stButton"] > button {
        width: 100%;
        border-radius: 8px;
        min-height: 60px;
        font-weight: 800;
        font-size: 22px;
    }

    div[data-testid="stSlider"] {
        padding-top: 8px;
        padding-bottom: 8px;
    }

    div[data-testid="stSlider"] label p {
        font-size: 20px;
        font-weight: 800;
    }

    div[data-testid="stMetricLabel"] p {
        font-size: 20px;
        color: #a8b4c2;
    }

    div[data-testid="stMetricValue"] {
        font-size: 34px;
        font-weight: 800;
    }

    div[data-testid="stCaptionContainer"] {
        font-size: 18px;
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


def init_state():
    if "compressor_on" not in st.session_state:
        st.session_state.compressor_on = True
    if "api_base_url" not in st.session_state:
        st.session_state.api_base_url = "http://localhost:8000"
    if "live_refresh" not in st.session_state:
        st.session_state.live_refresh = True


def set_compressor_power(is_on):
    st.session_state.compressor_on = is_on
    api_request("POST", "/simulator/power", {"compressor_on": is_on})


def api_request(method, path, payload=None, timeout=2.5):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{st.session_state.api_base_url}{path}",
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


def fetch_snapshot():
    st.session_state.api_error = ""
    return api_request("GET", "/simulator/status")


def update_server_config(config):
    return api_request("PUT", "/simulator/config", config)


def line_chart(df, y, title, unit, color):
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
        height=330,
        margin=dict(l=26, r=24, t=54, b=38),
        paper_bgcolor="#17212b",
        plot_bgcolor="#17212b",
        font=dict(color="#e8edf2", size=17),
        title=dict(text=f"{title} [{unit}]", font=dict(size=24)),
        xaxis=dict(
            gridcolor="#2b3d4f",
            zerolinecolor="#2b3d4f",
            title=dict(text="시간", font=dict(size=18)),
            tickfont=dict(size=16),
        ),
        yaxis=dict(
            gridcolor="#2b3d4f",
            zerolinecolor="#2b3d4f",
            tickfont=dict(size=16),
        ),
        showlegend=False,
    )
    return fig


def metric_card(label, value, unit):
    st.markdown(
        f"""
        <div class="status-card">
            <div class="status-label">{label}</div>
            <div>
                <span class="status-value">{value}</span>
                <span class="status-unit">{unit}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
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
snapshot = fetch_snapshot()
server_available = snapshot is not None

default_config = {
    "time_mode": "production",
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
st.session_state.compressor_on = current_power

# =========================
# 머리글
# =========================
left, right = st.columns([4, 1])

with left:
    st.markdown(
        """
        <div class="main-title">압축공기 누설 및 유휴설비 절전 알림 시스템</div>
        <div class="sub-title">비생산 시간대의 공기 사용량, 소음, 전류 패턴을 비교해 누설과 낭비 가능성을 알립니다.</div>
        """,
        unsafe_allow_html=True,
    )

if not server_available:
    st.error(f"서버 연결 실패: {st.session_state.get('api_error', '응답 없음')}")
    st.info("먼저 터미널에서 `uv run uvicorn main:app --reload --port 8000` 서버를 실행해주세요.")

# =========================
# 조작부
# =========================
control_col, state_col = st.columns([1.15, 1])

with control_col:
    st.markdown('<div class="panel-title">운전 조작</div>', unsafe_allow_html=True)
    on_col, off_col = st.columns(2)
    with on_col:
        st.button(
            "컴프레셔 켜기",
            type="primary",
            disabled=st.session_state.compressor_on,
            on_click=set_compressor_power,
            args=(True,),
        )
    with off_col:
        st.button(
            "컴프레셔 끄기",
            disabled=not st.session_state.compressor_on,
            on_click=set_compressor_power,
            args=(False,),
        )

    mode_options = {"생산 시간": "production", "비생산 시간": "non_production"}
    current_mode_label = "비생산 시간" if config["time_mode"] == "non_production" else "생산 시간"
    time_mode_label = st.radio(
        "시간대",
        list(mode_options.keys()),
        index=list(mode_options.keys()).index(current_mode_label),
        horizontal=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        load_percent = st.slider("부하율 (%)", 0, 100, int(config["load_percent"]), 1)
        leak_level = st.slider("누설 정도 (%)", 0, 100, int(config["leak_level"]), 1)
        vibration_base = st.slider("진동 기준값 (g RMS)", 0.001, 0.050, float(config["vibration_base"]), 0.001)
    with c2:
        idle_power_level = st.slider("유휴 전력 정도 (%)", 0, 100, int(config["idle_power_level"]), 1)
        current_base = st.slider("전류 기준값 (A)", 0.2, 8.0, float(config["current_base"]), 0.1)
        pressure_target = st.slider("목표 압력 (bar)", 0.2, 10.0, float(config["pressure_target"]), 0.1)
    with c3:
        temperature_base = st.slider("기준 온도 (℃)", 10.0, 60.0, float(config["temperature_base"]), 0.5)
        air_frequency = st.slider("공기 주파수 (Hz)", 0, 500, int(config["air_frequency"]), 1)

    live_refresh = st.toggle("실시간 자동 갱신", key="live_refresh")

config_payload = {
    "time_mode": mode_options[time_mode_label],
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

refresh_interval = "1s" if live_refresh else None


def build_live_values():
    live_snapshot = fetch_snapshot()
    active_state = live_snapshot["status"] if live_snapshot else "off"
    history = live_snapshot["history"] if live_snapshot else []
    alerts = live_snapshot["alerts"] if live_snapshot else []
    df = pd.DataFrame(history)
    latest = live_snapshot["latest"] if live_snapshot else {
        "time_mode": "production",
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
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    latest = {
        "time_mode": "production",
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
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        **latest,
    }
    return active_state, df, latest, alerts


@st.fragment(run_every=refresh_interval)
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


@st.fragment(run_every=refresh_interval)
def render_state_panel():
    active_state, _, _, _ = build_live_values()
    state_panel(active_state)


@st.fragment(run_every=refresh_interval)
def render_live_dashboard():
    active_state, df, latest, alerts = build_live_values()
    st.session_state.compressor_on = active_state != "off"

    st.write("")

    # =========================
    # 주요 수치
    # =========================
    c1, c2, c3 = st.columns(3)

    with c1:
        metric_card("공기 사용량", f'{latest["air_flow"]:.1f}', "L/min")

    with c2:
        metric_card("소음", f'{latest["sound_db"]:.1f}', "dB")

    with c3:
        metric_card("전류", f'{latest["current"]:.2f}', "A")

    c4, c5, c6 = st.columns(3)

    with c4:
        metric_card("압력", f'{latest["pressure"]:.2f}', "bar")

    with c5:
        metric_card("온도", f'{latest["temperature"]:.1f}', "℃")

    with c6:
        metric_card("진동", f'{latest["vibration"]:.3f}', "g RMS")

    st.write("")

    is_non_production = latest.get("time_mode") == "non_production"
    leak_text = "누설 의심" if latest.get("leak_alert") else "정상"
    idle_text = "낭비 의심" if latest.get("idle_power_alert") else "정상"
    mode_text = "비생산 시간" if is_non_production else "생산 시간"

    a1, a2, a3 = st.columns(3)
    a1.metric("시간대", mode_text)
    a2.metric("압축공기 누설", leak_text)
    a3.metric("유휴 전력 낭비", idle_text)

    alert_class = "alert-danger" if latest.get("alert_level", 0) else "alert-normal"
    alert_title = "점검 알림 발생" if latest.get("alert_level", 0) else "현재 감지 상태 정상"
    alert_copy = (
        "비생산 시간대에 기준보다 높은 공기 사용량, 소음 또는 전류가 지속되고 있습니다. 알림 이력을 확인하고 우선 점검 위치를 확인하세요."
        if latest.get("alert_level", 0)
        else "비생산 시간대 기준을 초과하는 누설 또는 유휴 전력 낭비 패턴이 지속되지 않았습니다."
    )
    st.markdown(
        (
            f'<div class="alert-panel {alert_class}">'
            f'<div class="alert-title">{alert_title}</div>'
            f'<div class="alert-copy">{alert_copy}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    st.write("")

    # =========================
    # 그래프
    # =========================
    row1_col1, row1_col2 = st.columns(2)

    with row1_col1:
        st.plotly_chart(
            line_chart(df, "air_flow", "공기 사용량", "L/min", "rgba(57, 217, 138, 1)"),
            width="stretch",
            config={"displayModeBar": False},
        )

    with row1_col2:
        st.plotly_chart(
            line_chart(df, "sound_db", "소음", "dB", "rgba(245, 166, 35, 1)"),
            width="stretch",
            config={"displayModeBar": False},
        )

    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        st.plotly_chart(
            line_chart(df, "current", "전류", "A", "rgba(68, 138, 255, 1)"),
            width="stretch",
            config={"displayModeBar": False},
        )

    with row2_col2:
        st.plotly_chart(
            line_chart(df, "pressure", "압력", "bar", "rgba(255, 96, 92, 1)"),
            width="stretch",
            config={"displayModeBar": False},
        )

    row3_col1, row3_col2 = st.columns(2)

    with row3_col1:
        st.plotly_chart(
            line_chart(df, "temperature", "온도", "℃", "rgba(150, 120, 255, 1)"),
            width="stretch",
            config={"displayModeBar": False},
        )

    with row3_col2:
        st.plotly_chart(
            line_chart(df, "vibration", "진동", "g RMS", "rgba(94, 214, 214, 1)"),
            width="stretch",
            config={"displayModeBar": False},
        )

    # =========================
    # 하단 상태
    # =========================
    st.write("")

    alarm_count = int(df["alarm_level"].iloc[-80:].sum()) if "alarm_level" in df else 0
    alarm_text = "점검 필요" if alarm_count > 0 else "정상"
    motor_state = "꺼짐" if active_state == "off" else "켜짐"

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("모터 상태", motor_state)
    b2.metric("공기 주파수", f'{latest["frequency"]:.2f} Hz')
    b3.metric("부하율", f'{latest["operation"]:.1f} %')
    b4.metric("알람", alarm_text)

    st.markdown('<div class="panel-title">알림 및 점검 이력</div>', unsafe_allow_html=True)
    if alerts:
        st.dataframe(
            pd.DataFrame(alerts).rename(
                columns={
                    "timestamp": "발생 시간",
                    "type": "알림 유형",
                    "priority": "우선순위",
                    "location": "점검 위치",
                    "message": "내용",
                }
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("아직 기록된 누설 또는 유휴 전력 낭비 알림이 없습니다.")

    server_time = latest.get("timestamp", datetime.now().strftime("%H:%M:%S"))
    st.caption(f"마지막 수신 시간: {server_time}")


with right:
    render_status_badge()

with state_col:
    render_state_panel()

render_live_dashboard()
