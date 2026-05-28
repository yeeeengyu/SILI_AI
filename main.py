from collections import deque
from datetime import datetime
import json
from math import sin
from pathlib import Path
from random import Random
from statistics import median
from threading import RLock
from time import monotonic
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError


app = FastAPI(title="Compressor Simulator API")

EQUIPMENT_STORE_PATH = Path(__file__).with_name("equipment_store.json")
LEAK_BASELINE_MIN_SAMPLES = 20
LEAK_BASELINE_MAX_SAMPLES = 120
LEAK_BASELINE_SIGMA_MULTIPLIER = 3.0
LEAK_AIR_FLOW_SIGMA_FLOOR = 0.8
LEAK_SOUND_DB_SIGMA_FLOOR = 0.8
LEAK_BASELINE_LEARN_SCORE_LIMIT = 70
LEAK_SCENARIO_ALERT_LEVEL = 70
IDLE_CURRENT_RATIO_THRESHOLD = 0.42
VIBRATION_ALARM_THRESHOLD = 0.045
CURRENT_ALARM_RATIO_THRESHOLD = 1.35
TEMPERATURE_ALARM_DELTA = 8.0
PRESSURE_LOSS_ALERT_RATIO = 0.12
ALERT_SUSTAIN_COUNT = 4
DEFAULT_WASTE_DETECTION_FIELDS = [
    "air_flow",
    "sound_db",
    "current",
    "pressure",
    "vibration",
    "temperature",
]
ALERT_TYPE_FIELDS = {
    "압축공기 누설 의심": {"pressure", "air_flow", "sound_db"},
    "압력 유지 전력 낭비 의심": {"pressure", "current"},
    "유휴 설비 전력 낭비 의심": {"pressure", "current"},
}

WasteDetectionField = Literal["air_flow", "sound_db", "current", "pressure", "vibration", "temperature"]


class SimulatorConfig(BaseModel):
    time_mode: Literal["production", "non_production"] = "production"
    usage_start_time: str = Field("08:00", pattern=r"^\d{2}:\d{2}$")
    usage_end_time: str = Field("18:00", pattern=r"^\d{2}:\d{2}$")
    lunch_start_time: str = Field("12:00", pattern=r"^\d{2}:\d{2}$")
    lunch_end_time: str = Field("13:00", pattern=r"^\d{2}:\d{2}$")
    rest_start_time: str = Field("15:00", pattern=r"^\d{2}:\d{2}$")
    rest_end_time: str = Field("15:15", pattern=r"^\d{2}:\d{2}$")
    load_percent: int = Field(68, ge=0, le=100)
    leak_level: int = Field(0, ge=0, le=100)
    idle_power_level: int = Field(0, ge=0, le=100)
    vibration_base: float = Field(0.014, ge=0.001, le=0.05)
    current_base: float = Field(2.2, ge=0.2, le=8.0)
    pressure_target: float = Field(4.2, ge=0.2, le=10.0)
    temperature_base: float = Field(29.0, ge=10.0, le=60.0)
    air_frequency: int = Field(412, ge=0, le=500)
    waste_detection_fields: list[WasteDetectionField] = Field(
        default_factory=lambda: DEFAULT_WASTE_DETECTION_FIELDS.copy()
    )


class PowerCommand(BaseModel):
    compressor_on: bool


class EquipmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    area: str = Field(..., min_length=1, max_length=40)


class Simulator:
    def __init__(self, config=None, compressor_on=True):
        self.lock = RLock()
        self.random = Random(17)
        self.config = config or SimulatorConfig()
        self.compressor_on = compressor_on
        self.sequence = 0
        self.last_tick = monotonic()
        self.pressure = self.config.pressure_target * 0.9
        self.temperature = self.config.temperature_base + 2.0
        self.vibration = self.config.vibration_base
        self.current = self.config.current_base
        self.frequency = self.config.air_frequency
        self.air_flow = 0.0
        self.sound_db = 45.0
        self.history = deque(maxlen=180)
        self.alert_events = deque(maxlen=20)
        self.leak_air_baseline = deque(maxlen=LEAK_BASELINE_MAX_SAMPLES)
        self.leak_sound_baseline = deque(maxlen=LEAK_BASELINE_MAX_SAMPLES)
        self.leak_sustain_count = 0
        self.idle_power_sustain_count = 0

        for _ in range(80):
            self._step(0.5)

    def classify_state(self):
        if not self.compressor_on:
            return "off"
        if self._current_time_mode() == "production":
            return "running"
        return "idle"

    def update_config(self, config):
        with self.lock:
            self._advance()
            self.config = config.model_copy(update={"time_mode": self._time_mode_for_config(config)})
            self._sync_alert_state_with_detection_fields()
            self._step(0.45)
            self.last_tick = monotonic()
            return self.snapshot()

    def set_power(self, compressor_on):
        with self.lock:
            self._advance()
            self.compressor_on = compressor_on
            self._step(0.45)
            self.last_tick = monotonic()
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            self._advance()
            latest = self.history[-1] if self.history else self._step(0.5)
            return {
                "compressor_on": self.compressor_on,
                "status": self.classify_state(),
                "config": self.config.model_dump(),
                "latest": latest,
                "history": list(self.history),
                "alerts": list(self.alert_events),
            }

    def _advance(self):
        now = monotonic()
        elapsed = now - self.last_tick
        step_count = min(12, max(1, int(elapsed / 0.45)))

        if elapsed < 0.35 and self.history:
            return

        for _ in range(step_count):
            self._step(0.45)
        self.last_tick = now

    def _step(self, dt):
        time_mode = self._current_time_mode()
        time_mode_reason = self._current_time_mode_reason()
        state = self.classify_state()
        load = self.config.load_percent / 100 if time_mode == "production" else 0.0
        is_non_production = time_mode == "non_production"
        leak_ratio = self.config.leak_level / 100
        idle_power_ratio = self.config.idle_power_level / 100
        pressure_loss_ratio = min(1.0, leak_ratio + (idle_power_ratio if is_non_production else idle_power_ratio * 0.25))
        self.sequence += 1
        phase = self.sequence * 0.22
        noise = self.random.uniform

        if state == "off":
            operation = 0.0
            target_pressure = max(
                self.pressure - self.config.pressure_target * (0.005 + pressure_loss_ratio * 0.06),
                0.0,
            )
            target_current = 0.03
            target_vibration = 0.002
            target_temperature = self.config.temperature_base - 1.5
            target_frequency = 0.0
            target_air_flow = 0.0
            target_sound_db = 38.0
        elif state == "idle":
            recovery_effort = min(1.0, 0.08 + pressure_loss_ratio * 0.92)
            operation = 4.0 + recovery_effort * 38.0 + 2.0 * sin(phase)
            target_pressure = self.config.pressure_target * max(
                0.55,
                0.98 - pressure_loss_ratio * 0.42 + 0.015 * sin(phase * 0.8),
            )
            target_current = self.config.current_base * (0.10 + recovery_effort * 0.72 + 0.02 * sin(phase))
            target_vibration = self.config.vibration_base * (0.35 + recovery_effort * 0.55 + 0.04 * sin(phase * 1.4))
            target_temperature = self.config.temperature_base + 0.4 + recovery_effort * 2.8 + 0.25 * sin(phase * 0.7)
            target_frequency = self.config.air_frequency * (0.12 + recovery_effort * 0.45)
            target_air_flow = 0.8 + pressure_loss_ratio * 58.0
            target_sound_db = 39.0 + recovery_effort * 18.0 + leak_ratio * 8.0
        else:
            recovery_effort = min(1.0, load * 0.72 + pressure_loss_ratio * 0.42)
            operation = 36 + recovery_effort * 62 + 3.5 * sin(phase * 0.6)
            pulse = 1.0 if self.sequence % 36 in (0, 1, 2) else 0.0
            target_pressure = self.config.pressure_target * max(
                0.62,
                0.99 - load * 0.10 - pressure_loss_ratio * 0.28,
            )
            target_current = self.config.current_base * (0.42 + recovery_effort * 0.82) + pulse * 0.32
            target_vibration = self.config.vibration_base * (0.72 + recovery_effort * 0.85) + pulse * 0.008
            target_temperature = self.config.temperature_base + 1.8 + recovery_effort * 6.2 + 0.7 * sin(phase * 0.45)
            target_frequency = self.config.air_frequency * (0.55 + recovery_effort * 0.45)
            target_air_flow = 8.0 + load * 145.0 + pressure_loss_ratio * 50.0
            target_sound_db = 47.0 + recovery_effort * 21.0 + leak_ratio * 10.0

        if state == "off":
            self.pressure = target_pressure
        else:
            self.pressure = self._ease(self.pressure, target_pressure, 0.16) + noise(-0.025, 0.025)
        self.current = self._ease(self.current, target_current, 0.22) + noise(-0.035, 0.035)
        self.vibration = self._ease(self.vibration, target_vibration, 0.24) + noise(-0.0012, 0.0012)
        self.temperature = self._ease(self.temperature, target_temperature, 0.08) + noise(-0.08, 0.08)
        self.frequency = self._ease(self.frequency, target_frequency, 0.20) + noise(-0.8, 0.8)
        self.air_flow = self._ease(self.air_flow, target_air_flow, 0.28) + noise(-0.7, 0.7)
        self.sound_db = self._ease(self.sound_db, target_sound_db, 0.22) + noise(-0.6, 0.6)

        enabled_detection_fields = set(self.config.waste_detection_fields)
        use_air_flow = "air_flow" in enabled_detection_fields
        use_sound_db = "sound_db" in enabled_detection_fields
        use_current = "current" in enabled_detection_fields
        use_pressure = "pressure" in enabled_detection_fields
        use_vibration = "vibration" in enabled_detection_fields
        use_temperature = "temperature" in enabled_detection_fields
        pressure_loss = max(self.config.pressure_target - self.pressure, 0.0)
        pressure_loss_threshold = self.config.pressure_target * PRESSURE_LOSS_ALERT_RATIO
        pressure_score = self._threshold_score(pressure_loss, pressure_loss_threshold) if use_pressure else 0
        pressure_loss_detected = is_non_production and use_pressure and pressure_score >= 100

        leak_baseline = self._leak_baseline()
        baseline_ready = leak_baseline["ready"]
        leak_score = 0
        leak_suspected = False
        leak_scores = []
        if baseline_ready:
            if use_air_flow:
                leak_scores.append(
                    self._dynamic_score(self.air_flow, leak_baseline["air_median"], leak_baseline["air_limit"])
                )
            if use_sound_db:
                leak_scores.append(
                    self._dynamic_score(self.sound_db, leak_baseline["sound_median"], leak_baseline["sound_limit"])
                )
            if leak_scores:
                leak_score = min(leak_scores)
                leak_suspected = all(score >= 100 for score in leak_scores)
        has_leak_inputs = use_air_flow or use_sound_db or use_pressure
        leak_score = max(leak_score, pressure_score, self.config.leak_level) if has_leak_inputs else 0
        scenario_leak_detected = has_leak_inputs and self.config.leak_level >= LEAK_SCENARIO_ALERT_LEVEL
        leak_detected = scenario_leak_detected or pressure_loss_detected or (is_non_production and baseline_ready and leak_suspected)

        idle_power_threshold = self.config.current_base * IDLE_CURRENT_RATIO_THRESHOLD
        current_idle_detected = use_current and self.current > idle_power_threshold
        idle_power_detected = is_non_production and self.compressor_on and (pressure_loss_detected or current_idle_detected)
        self.leak_sustain_count = self.leak_sustain_count + 1 if leak_detected else 0
        self.idle_power_sustain_count = self.idle_power_sustain_count + 1 if idle_power_detected else 0
        leak_alert = self.leak_sustain_count >= ALERT_SUSTAIN_COUNT
        idle_power_alert = self.idle_power_sustain_count >= ALERT_SUSTAIN_COUNT
        alert_level = int(leak_alert) + int(idle_power_alert)
        self._record_alerts(leak_alert, idle_power_alert)

        if (
            is_non_production
            and self.config.leak_level == 0
            and not leak_alert
            and leak_score < LEAK_BASELINE_LEARN_SCORE_LIMIT
        ):
            self.leak_air_baseline.append(max(self.air_flow, 0))
            self.leak_sound_baseline.append(max(self.sound_db, 0))

        current_idle_score = self._threshold_score(self.current, idle_power_threshold) if is_non_production and use_current else 0
        idle_power_score = max(pressure_score if is_non_production and use_pressure else 0, current_idle_score)
        vibration_score = self._threshold_score(self.vibration, VIBRATION_ALARM_THRESHOLD) if use_vibration else 0
        current_score = (
            self._threshold_score(self.current, self.config.current_base * CURRENT_ALARM_RATIO_THRESHOLD)
            if use_current
            else 0
        )
        temperature_score = (
            self._threshold_score(self.temperature, self.config.temperature_base + TEMPERATURE_ALARM_DELTA)
            if use_temperature
            else 0
        )
        anomaly_score = max(leak_score, idle_power_score, vibration_score, current_score, pressure_score, temperature_score)

        alarm_level = int(
            (use_vibration and self.vibration > VIBRATION_ALARM_THRESHOLD)
            or (use_current and self.current > self.config.current_base * CURRENT_ALARM_RATIO_THRESHOLD)
            or pressure_loss_detected
            or (use_temperature and self.temperature > self.config.temperature_base + TEMPERATURE_ALARM_DELTA)
            or alert_level > 0
        )

        sample = {
            "time": self.sequence,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "time_mode": time_mode,
            "time_mode_reason": time_mode_reason,
            "usage_start_time": self.config.usage_start_time,
            "usage_end_time": self.config.usage_end_time,
            "lunch_start_time": self.config.lunch_start_time,
            "lunch_end_time": self.config.lunch_end_time,
            "rest_start_time": self.config.rest_start_time,
            "rest_end_time": self.config.rest_end_time,
            "vibration": round(max(self.vibration, 0), 4),
            "current": round(max(self.current, 0), 3),
            "pressure": round(max(self.pressure, 0), 3),
            "temperature": round(self.temperature, 2),
            "frequency": round(max(self.frequency, 0), 2),
            "air_flow": round(max(self.air_flow, 0), 2),
            "sound_db": round(max(self.sound_db, 0), 1),
            "operation": round(max(min(operation, 100), 0), 1),
            "alarm_level": alarm_level,
            "leak_alert": leak_alert,
            "idle_power_alert": idle_power_alert,
            "alert_level": alert_level,
            "anomaly_score": anomaly_score,
            "leak_score": leak_score,
            "idle_power_score": idle_power_score,
            "current_score": current_score,
            "pressure_score": pressure_score,
            "vibration_score": vibration_score,
            "temperature_score": temperature_score,
            "baseline_ready": baseline_ready,
            "baseline_count": leak_baseline["count"],
            "baseline_source": "dynamic",
            "baseline_air_flow": round(leak_baseline["air_median"], 2),
            "baseline_sound_db": round(leak_baseline["sound_median"], 1),
            "baseline_air_flow_limit": round(leak_baseline["air_limit"], 2),
            "baseline_sound_db_limit": round(leak_baseline["sound_limit"], 1),
            "leak_sustain_count": self.leak_sustain_count,
            "idle_power_sustain_count": self.idle_power_sustain_count,
            "waste_detection_fields": list(self.config.waste_detection_fields),
        }
        self.history.append(sample)
        return sample

    def _record_alerts(self, leak_alert, idle_power_alert):
        if leak_alert and self.leak_sustain_count == ALERT_SUSTAIN_COUNT:
            self.alert_events.appendleft(
                {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "type": "압축공기 누설 의심",
                    "priority": "높음",
                    "location": "압축공기 라인",
                    "fields": ["pressure", "air_flow", "sound_db"],
                    "message": "미사용 시간대에 압력 손실이 기준선을 벗어났고, 보조 센서 값이 함께 변동될 수 있습니다.",
                }
            )
        if idle_power_alert and self.idle_power_sustain_count == ALERT_SUSTAIN_COUNT:
            self.alert_events.appendleft(
                {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "type": "압력 유지 전력 낭비 의심",
                    "priority": "중간",
                    "location": "압력 유지 운전",
                    "fields": ["pressure", "current"],
                    "message": "미사용 시간대 압력 손실을 보충하기 위해 전류가 소모되는 패턴이 유지됩니다.",
                }
            )

    def _sync_alert_state_with_detection_fields(self):
        enabled_fields = set(self.config.waste_detection_fields)
        if not ({"pressure", "current"} & enabled_fields):
            self.idle_power_sustain_count = 0
        if not ({"pressure", "air_flow", "sound_db"} & enabled_fields):
            self.leak_sustain_count = 0
        self.alert_events = deque(
            (
                alert
                for alert in self.alert_events
                if self._alert_applies_to_fields(alert, enabled_fields)
            ),
            maxlen=self.alert_events.maxlen,
        )

    @staticmethod
    def _alert_applies_to_fields(alert, enabled_fields):
        alert_fields = set(alert.get("fields") or ALERT_TYPE_FIELDS.get(alert.get("type"), set()))
        return not alert_fields or bool(alert_fields & enabled_fields)

    def _current_time_mode(self):
        return self._time_mode_for_config(self.config)

    def _current_time_mode_reason(self):
        return self._time_mode_reason_for_config(self.config)

    def _time_mode_for_config(self, config):
        reason = self._time_mode_reason_for_config(config)
        return "production" if reason == "working_hours" else "non_production"

    def _time_mode_reason_for_config(self, config):
        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute
        start_minutes = self._minutes_from_hhmm(config.usage_start_time, 8 * 60)
        end_minutes = self._minutes_from_hhmm(config.usage_end_time, 18 * 60)
        lunch_start_minutes = self._minutes_from_hhmm(config.lunch_start_time, 12 * 60)
        lunch_end_minutes = self._minutes_from_hhmm(config.lunch_end_time, 13 * 60)
        rest_start_minutes = self._minutes_from_hhmm(config.rest_start_time, 15 * 60)
        rest_end_minutes = self._minutes_from_hhmm(config.rest_end_time, 15 * 60 + 15)

        if not self._is_minute_in_period(current_minutes, start_minutes, end_minutes, same_time_means_all_day=True):
            return "off_hours"
        if self._is_minute_in_period(current_minutes, lunch_start_minutes, lunch_end_minutes):
            return "lunch_break"
        if self._is_minute_in_period(current_minutes, rest_start_minutes, rest_end_minutes):
            return "rest_break"
        return "working_hours"

    @staticmethod
    def _minutes_from_hhmm(value, fallback):
        try:
            hour_text, minute_text = value.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except (AttributeError, ValueError):
            return fallback
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour * 60 + minute
        return fallback

    @staticmethod
    def _is_minute_in_period(current_minutes, start_minutes, end_minutes, same_time_means_all_day=False):
        if start_minutes == end_minutes:
            return same_time_means_all_day
        if start_minutes < end_minutes:
            return start_minutes <= current_minutes < end_minutes
        return current_minutes >= start_minutes or current_minutes < end_minutes

    def _leak_baseline(self):
        count = min(len(self.leak_air_baseline), len(self.leak_sound_baseline))
        if count == 0:
            return {
                "ready": False,
                "count": 0,
                "air_median": 0.0,
                "sound_median": 0.0,
                "air_limit": 0.0,
                "sound_limit": 0.0,
            }

        air_values = list(self.leak_air_baseline)
        sound_values = list(self.leak_sound_baseline)
        air_median, air_sigma = self._robust_center_sigma(air_values, LEAK_AIR_FLOW_SIGMA_FLOOR)
        sound_median, sound_sigma = self._robust_center_sigma(sound_values, LEAK_SOUND_DB_SIGMA_FLOOR)
        return {
            "ready": count >= LEAK_BASELINE_MIN_SAMPLES,
            "count": count,
            "air_median": air_median,
            "sound_median": sound_median,
            "air_limit": air_median + LEAK_BASELINE_SIGMA_MULTIPLIER * air_sigma,
            "sound_limit": sound_median + LEAK_BASELINE_SIGMA_MULTIPLIER * sound_sigma,
        }

    @staticmethod
    def _robust_center_sigma(values, sigma_floor):
        center = median(values)
        deviations = [abs(value - center) for value in values]
        mad = median(deviations)
        robust_sigma = mad * 1.4826
        return center, max(robust_sigma, sigma_floor)

    @staticmethod
    def _dynamic_score(value, center, limit):
        spread = limit - center
        if spread <= 0:
            return 0
        return round(max(0, min(((value - center) / spread) * 100, 100)))

    @staticmethod
    def _threshold_score(value, threshold):
        if threshold <= 0:
            return 0
        return round(max(0, min((value / threshold) * 100, 100)))

    @staticmethod
    def _ease(current, target, ratio):
        return current + (target - current) * ratio


class EquipmentSlot:
    def __init__(self, equipment_id, name, area, config=None, compressor_on=True):
        self.id = equipment_id
        self.name = name
        self.area = area
        self.simulator = Simulator(config=config, compressor_on=compressor_on)

    def metadata(self):
        return {
            "id": self.id,
            "name": self.name,
            "area": self.area,
        }

    def snapshot(self):
        snapshot = self.simulator.snapshot()
        snapshot["equipment"] = self.metadata()
        return snapshot

    def to_record(self):
        with self.simulator.lock:
            return {
                "id": self.id,
                "name": self.name,
                "area": self.area,
                "config": self.simulator.config.model_dump(),
                "compressor_on": self.simulator.compressor_on,
            }


class EquipmentRegistry:
    def __init__(self, storage_path=EQUIPMENT_STORE_PATH):
        self.lock = RLock()
        self.storage_path = storage_path
        self.next_id = 1
        self.slots = {}
        self.default_id = None
        self._load()
        if not self.slots:
            slot = self._create_slot("equipment-1", "컴프레셔 1", "1구역")
            self.default_id = slot.id
            self.next_id = 2
            self._save()

    def create(self, command):
        with self.lock:
            equipment_id = f"equipment-{self.next_id}"
            self.next_id += 1
            slot = self._create_slot(equipment_id, command.name.strip(), command.area.strip())
            self.default_id = slot.id
            self._save()
            return slot

    def list_metadata(self):
        with self.lock:
            return [slot.metadata() for slot in self.slots.values()]

    def get(self, equipment_id=None):
        with self.lock:
            selected_id = equipment_id or self.default_id
            slot = self.slots.get(selected_id)
            if slot is None:
                raise HTTPException(status_code=404, detail="Equipment not found")
            return slot

    def save(self):
        with self.lock:
            self._save()

    def _create_slot(self, equipment_id, name, area, config=None, compressor_on=True):
        slot = EquipmentSlot(equipment_id, name, area, config=config, compressor_on=compressor_on)
        self.slots[equipment_id] = slot
        return slot

    def _load(self):
        if not self.storage_path.exists():
            return

        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        for record in data.get("equipment", []):
            equipment_id = str(record.get("id") or "").strip()
            name = str(record.get("name") or "").strip()
            area = str(record.get("area") or "").strip()
            if not equipment_id or not name or not area:
                continue

            try:
                config = SimulatorConfig.model_validate(record.get("config") or {})
            except ValidationError:
                config = SimulatorConfig()
            compressor_on = bool(record.get("compressor_on", True))
            self._create_slot(equipment_id, name, area, config=config, compressor_on=compressor_on)

        saved_next_id = data.get("next_id")
        if isinstance(saved_next_id, int) and saved_next_id > 0:
            self.next_id = saved_next_id
        else:
            self.next_id = self._next_id_from_slots()

        saved_default_id = data.get("default_equipment_id")
        if saved_default_id in self.slots:
            self.default_id = saved_default_id
        elif self.slots:
            self.default_id = next(iter(self.slots))

    def _save(self):
        data = {
            "next_id": self.next_id,
            "default_equipment_id": self.default_id,
            "equipment": [slot.to_record() for slot in self.slots.values()],
        }
        tmp_path = self.storage_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.storage_path)

    def _next_id_from_slots(self):
        max_id = 0
        for equipment_id in self.slots:
            if not equipment_id.startswith("equipment-"):
                continue
            try:
                max_id = max(max_id, int(equipment_id.removeprefix("equipment-")))
            except ValueError:
                continue
        return max_id + 1


equipment_registry = EquipmentRegistry()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/equipment")
def list_equipment():
    return {
        "equipment": equipment_registry.list_metadata(),
        "default_equipment_id": equipment_registry.default_id,
    }


@app.post("/equipment")
def create_equipment(command: EquipmentCreate):
    slot = equipment_registry.create(command)
    return {
        "equipment": slot.metadata(),
        "snapshot": slot.snapshot(),
    }


@app.get("/simulator/status")
def get_simulator_status(equipment_id: str | None = None):
    return equipment_registry.get(equipment_id).snapshot()


@app.put("/simulator/config")
def update_simulator_config(config: SimulatorConfig, equipment_id: str | None = None):
    slot = equipment_registry.get(equipment_id)
    snapshot = slot.simulator.update_config(config)
    snapshot["equipment"] = slot.metadata()
    equipment_registry.save()
    return snapshot


@app.post("/simulator/power")
def set_simulator_power(command: PowerCommand, equipment_id: str | None = None):
    slot = equipment_registry.get(equipment_id)
    snapshot = slot.simulator.set_power(command.compressor_on)
    snapshot["equipment"] = slot.metadata()
    equipment_registry.save()
    return snapshot
