from collections import deque
from datetime import datetime
from math import sin
from random import Random
from threading import RLock
from time import monotonic
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(title="Compressor Simulator API")


class SimulatorConfig(BaseModel):
    time_mode: Literal["production", "non_production"] = "production"
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


class Simulator:
    def __init__(self):
        self.lock = RLock()
        self.random = Random(17)
        self.config = SimulatorConfig()
        self.compressor_on = True
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
        self.leak_sustain_count = 0
        self.idle_power_sustain_count = 0

        for _ in range(80):
            self._step(0.5)

    def classify_state(self):
        if not self.compressor_on:
            return "off"
        if self.config.load_percent >= 15:
            return "running"
        return "idle"

    def update_config(self, config):
        with self.lock:
            self._advance()
            self.config = config
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
        state = self.classify_state()
        load = self.config.load_percent / 100
        is_non_production = self.config.time_mode == "non_production"
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

        leak_detected = is_non_production and self.air_flow > 12.0 and self.sound_db > 48.0
        idle_power_detected = (
            is_non_production
            and self.compressor_on
            and self.current > self.config.current_base * 0.42
        )
        self.leak_sustain_count = self.leak_sustain_count + 1 if leak_detected else 0
        self.idle_power_sustain_count = self.idle_power_sustain_count + 1 if idle_power_detected else 0
        leak_alert = self.leak_sustain_count >= 4
        idle_power_alert = self.idle_power_sustain_count >= 4
        alert_level = int(leak_alert) + int(idle_power_alert)
        self._record_alerts(leak_alert, idle_power_alert)

        alarm_level = int(
            self.vibration > 0.045
            or self.current > self.config.current_base * 1.35
            or self.temperature > self.config.temperature_base + 8.0
            or alert_level > 0
        )

        sample = {
            "time": self.sequence,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "time_mode": self.config.time_mode,
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
        }
        self.history.append(sample)
        return sample

    def _record_alerts(self, leak_alert, idle_power_alert):
        if leak_alert and self.leak_sustain_count == 4:
            self.alert_events.appendleft(
                {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "type": "압축공기 누설 의심",
                    "priority": "높음",
                    "location": "압축공기 배관 주변",
                    "message": "비생산 시간대에 공기 사용량과 소음이 기준보다 높게 유지됩니다.",
                }
            )
        if idle_power_alert and self.idle_power_sustain_count == 4:
            self.alert_events.appendleft(
                {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "type": "유휴 설비 전력 낭비 의심",
                    "priority": "중간",
                    "location": "설비 전원부",
                    "message": "비생산 시간대에 전류 사용량이 기준보다 높게 유지됩니다.",
                }
            )

    @staticmethod
    def _ease(current, target, ratio):
        return current + (target - current) * ratio


simulator = Simulator()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/simulator/status")
def get_simulator_status():
    return simulator.snapshot()


@app.put("/simulator/config")
def update_simulator_config(config: SimulatorConfig):
    return simulator.update_config(config)


@app.post("/simulator/power")
def set_simulator_power(command: PowerCommand):
    return simulator.set_power(command.compressor_on)
