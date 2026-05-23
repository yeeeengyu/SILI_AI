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
ALERT_SUSTAIN_COUNT = 4


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
        self.sequence += 1
        phase = self.sequence * 0.22
        noise = self.random.uniform

        if state == "off":
            operation = 0.0
            target_pressure = self.pressure
            target_current = 0.03
            target_vibration = 0.002
            target_temperature = self.config.temperature_base - 1.5
            target_frequency = 0.0
            target_air_flow = 0.0
            target_sound_db = 38.0
        elif state == "idle":
            operation = 18 + 4 * sin(phase)
            target_pressure = self.config.pressure_target * (0.78 + 0.03 * sin(phase * 0.8))
            target_current = self.config.current_base * (0.28 + 0.04 * sin(phase)) + self.config.current_base * idle_power_ratio * 0.45
            target_vibration = self.config.vibration_base * (0.45 + 0.06 * sin(phase * 1.4))
            target_temperature = self.config.temperature_base + 1.0 + 0.25 * sin(phase * 0.7)
            target_frequency = self.config.air_frequency * 0.28
            target_air_flow = 2.0 + leak_ratio * 42.0 + max(load - 0.12, 0) * 28.0
            target_sound_db = 43.0 + leak_ratio * 20.0 + idle_power_ratio * 4.0
        else:
            operation = 45 + load * 55 + 3.5 * sin(phase * 0.6)
            pulse = 1.0 if self.sequence % 36 in (0, 1, 2) else 0.0
            target_pressure = self.config.pressure_target * (0.76 + 0.23 * load)
            target_current = self.config.current_base * (0.58 + 0.64 * load) + pulse * 0.32 + self.config.current_base * idle_power_ratio * 0.25
            target_vibration = self.config.vibration_base * (0.9 + 0.65 * load) + pulse * 0.008
            target_temperature = self.config.temperature_base + 2.5 + 5.8 * load + 0.7 * sin(phase * 0.45)
            target_frequency = self.config.air_frequency * (0.72 + 0.28 * load)
            target_air_flow = 12.0 + load * 150.0 + leak_ratio * 42.0
            target_sound_db = 51.0 + load * 16.0 + leak_ratio * 18.0

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

        leak_baseline = self._leak_baseline()
        baseline_ready = leak_baseline["ready"]
        leak_score = 0
        leak_suspected = False
        if baseline_ready:
            air_score = self._dynamic_score(self.air_flow, leak_baseline["air_median"], leak_baseline["air_limit"])
            sound_score = self._dynamic_score(self.sound_db, leak_baseline["sound_median"], leak_baseline["sound_limit"])
            leak_score = min(air_score, sound_score)
            leak_suspected = air_score >= 100 and sound_score >= 100
        leak_score = max(leak_score, self.config.leak_level)
        scenario_leak_detected = self.config.leak_level >= LEAK_SCENARIO_ALERT_LEVEL
        leak_detected = scenario_leak_detected or (is_non_production and baseline_ready and leak_suspected)

        idle_power_threshold = self.config.current_base * IDLE_CURRENT_RATIO_THRESHOLD
        idle_power_detected = is_non_production and self.compressor_on and self.current > idle_power_threshold
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

        idle_power_score = self._threshold_score(self.current, idle_power_threshold) if is_non_production else 0
        vibration_score = self._threshold_score(self.vibration, VIBRATION_ALARM_THRESHOLD)
        current_score = self._threshold_score(self.current, self.config.current_base * CURRENT_ALARM_RATIO_THRESHOLD)
        temperature_score = self._threshold_score(self.temperature, self.config.temperature_base + TEMPERATURE_ALARM_DELTA)
        anomaly_score = max(leak_score, idle_power_score, vibration_score, current_score, temperature_score)

        alarm_level = int(
            self.vibration > VIBRATION_ALARM_THRESHOLD
            or self.current > self.config.current_base * CURRENT_ALARM_RATIO_THRESHOLD
            or self.temperature > self.config.temperature_base + TEMPERATURE_ALARM_DELTA
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
            "baseline_ready": baseline_ready,
            "baseline_count": leak_baseline["count"],
            "baseline_source": "dynamic",
            "baseline_air_flow": round(leak_baseline["air_median"], 2),
            "baseline_sound_db": round(leak_baseline["sound_median"], 1),
            "baseline_air_flow_limit": round(leak_baseline["air_limit"], 2),
            "baseline_sound_db_limit": round(leak_baseline["sound_limit"], 1),
            "leak_sustain_count": self.leak_sustain_count,
            "idle_power_sustain_count": self.idle_power_sustain_count,
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
                    "location": "압축공기 배관 주변",
                    "message": "미사용 시간대에 공기 사용량과 소음이 최근 정상 기준선을 함께 초과했습니다.",
                }
            )
        if idle_power_alert and self.idle_power_sustain_count == ALERT_SUSTAIN_COUNT:
            self.alert_events.appendleft(
                {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "type": "유휴 설비 전력 낭비 의심",
                    "priority": "중간",
                    "location": "설비 전원부",
                    "message": f"비생산 시간대에 전류가 기준 전류의 {IDLE_CURRENT_RATIO_THRESHOLD:.0%}를 초과한 상태로 유지됩니다.",
                }
            )

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
