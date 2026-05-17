from collections import deque
from datetime import datetime
from math import sin
from random import Random
from statistics import median
from threading import RLock
from time import monotonic
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(title="Compressor Simulator API")

BASELINE_MIN_SAMPLES = 12
BASELINE_MAX_SAMPLES = 240
LEAK_ALERT_SCORE = 70
IDLE_POWER_ALERT_SCORE = 65


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
        self.baselines = {}
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

        anomaly = self._analyze_anomalies(state)
        leak_detected = is_non_production and anomaly["leak_score"] >= LEAK_ALERT_SCORE
        idle_power_detected = is_non_production and self.compressor_on and anomaly["idle_power_score"] >= IDLE_POWER_ALERT_SCORE
        self.leak_sustain_count = self.leak_sustain_count + 1 if leak_detected else 0
        self.idle_power_sustain_count = self.idle_power_sustain_count + 1 if idle_power_detected else 0
        leak_alert = self.leak_sustain_count >= 4
        idle_power_alert = self.idle_power_sustain_count >= 4
        alert_level = int(leak_alert) + int(idle_power_alert)
        self._record_alerts(leak_alert, idle_power_alert, anomaly)

        alarm_level = int(anomaly["overall_score"] >= 70 or alert_level > 0)

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
            "anomaly_score": anomaly["overall_score"],
            "leak_score": anomaly["leak_score"],
            "idle_power_score": anomaly["idle_power_score"],
            "baseline_ready": anomaly["baseline_ready"],
            "baseline_count": anomaly["baseline_count"],
            "baseline_source": anomaly["baseline_source"],
            "leak_sustain_count": self.leak_sustain_count,
            "idle_power_sustain_count": self.idle_power_sustain_count,
        }
        self.history.append(sample)
        self._record_baseline(state)
        return sample

    def _record_alerts(self, leak_alert, idle_power_alert, anomaly):
        if leak_alert and self.leak_sustain_count == 4:
            self.alert_events.appendleft(
                {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "type": "압축공기 누설 의심",
                    "priority": "높음",
                    "location": "압축공기 배관 주변",
                    "message": f"정상 기준선 대비 공기·소음 패턴 편차 점수가 {anomaly['leak_score']}점으로 지속됩니다.",
                }
            )
        if idle_power_alert and self.idle_power_sustain_count == 4:
            self.alert_events.appendleft(
                {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "type": "유휴 설비 전력 낭비 의심",
                    "priority": "중간",
                    "location": "설비 전원부",
                    "message": f"정상 기준선 대비 전류·진동 패턴 편차 점수가 {anomaly['idle_power_score']}점으로 지속됩니다.",
                }
            )

    def _analyze_anomalies(self, state):
        stats = self._baseline_stats(state)
        baseline_count = stats["count"]
        baseline_ready = baseline_count >= BASELINE_MIN_SAMPLES
        baseline_source = stats["source"]

        air_score = self._deviation_score(self.air_flow, stats.get("air_flow"), "high")
        sound_score = self._deviation_score(self.sound_db, stats.get("sound_db"), "high")
        current_score = self._deviation_score(self.current, stats.get("current"), "high")
        vibration_score = self._deviation_score(self.vibration, stats.get("vibration"), "high")
        temperature_score = self._deviation_score(self.temperature, stats.get("temperature"), "high")
        pressure_score = self._deviation_score(self.pressure, stats.get("pressure"), "low")

        leak_score = self._clamp_score(air_score * 0.55 + sound_score * 0.35 + pressure_score * 0.10)
        idle_power_score = self._clamp_score(current_score * 0.65 + vibration_score * 0.20 + temperature_score * 0.15)
        overall_score = self._clamp_score(max(leak_score, idle_power_score, vibration_score * 0.85))

        if not baseline_ready:
            baseline_ready = baseline_source == "estimated"

        return {
            "overall_score": overall_score,
            "leak_score": leak_score,
            "idle_power_score": idle_power_score,
            "baseline_ready": baseline_ready,
            "baseline_count": baseline_count,
            "baseline_source": baseline_source,
        }

    def _record_baseline(self, state):
        if self.config.leak_level > 0 or self.config.idle_power_level > 0:
            return

        key = self._baseline_key(state)
        if key not in self.baselines:
            self.baselines[key] = deque(maxlen=BASELINE_MAX_SAMPLES)

        self.baselines[key].append(
            {
                "air_flow": max(self.air_flow, 0),
                "sound_db": max(self.sound_db, 0),
                "current": max(self.current, 0),
                "vibration": max(self.vibration, 0),
                "temperature": self.temperature,
                "pressure": max(self.pressure, 0),
            }
        )

    def _baseline_stats(self, state):
        samples = list(self.baselines.get(self._baseline_key(state), ()))
        source = "learned" if len(samples) >= BASELINE_MIN_SAMPLES else "estimated"
        stats = {"count": len(samples), "source": source}
        if len(samples) < BASELINE_MIN_SAMPLES:
            samples = self._estimated_baseline_samples(state)

        for metric in ("air_flow", "sound_db", "current", "vibration", "temperature", "pressure"):
            values = sorted(sample[metric] for sample in samples)
            stats[metric] = {
                "median": median(values),
                "q1": self._percentile(values, 0.25),
                "q3": self._percentile(values, 0.75),
            }
        return stats

    def _baseline_key(self, state):
        load_band = int(self.config.load_percent / 10) * 10
        return (self.config.time_mode, state, load_band)

    def _estimated_baseline_samples(self, state):
        load = self.config.load_percent / 100
        if state == "off":
            normal = {
                "air_flow": 0.0,
                "sound_db": 38.0,
                "current": 0.03,
                "vibration": 0.002,
                "temperature": self.config.temperature_base - 1.5,
                "pressure": max(self.pressure, 0),
            }
        elif state == "idle":
            normal = {
                "air_flow": 2.0 + max(load - 0.12, 0) * 28.0,
                "sound_db": 43.0,
                "current": self.config.current_base * 0.28,
                "vibration": self.config.vibration_base * 0.45,
                "temperature": self.config.temperature_base + 1.0,
                "pressure": self.config.pressure_target * 0.78,
            }
        else:
            normal = {
                "air_flow": 12.0 + load * 150.0,
                "sound_db": 51.0 + load * 16.0,
                "current": self.config.current_base * (0.58 + 0.64 * load),
                "vibration": self.config.vibration_base * (0.9 + 0.65 * load),
                "temperature": self.config.temperature_base + 2.5 + 5.8 * load,
                "pressure": self.config.pressure_target * (0.76 + 0.23 * load),
            }

        multipliers = (0.94, 0.97, 0.99, 1.0, 1.01, 1.03, 1.06)
        samples = []
        for multiplier in multipliers:
            samples.append(
                {
                    "air_flow": normal["air_flow"] * multiplier,
                    "sound_db": normal["sound_db"] + (multiplier - 1.0) * 18.0,
                    "current": normal["current"] * multiplier,
                    "vibration": normal["vibration"] * multiplier,
                    "temperature": normal["temperature"] + (multiplier - 1.0) * 4.0,
                    "pressure": normal["pressure"] * (2.0 - multiplier),
                }
            )
        return samples

    @staticmethod
    def _deviation_score(value, stats, direction):
        if not stats:
            return 0

        center = stats["median"]
        spread = max(stats["q3"] - stats["q1"], abs(center) * 0.05, 0.001)
        delta = value - center if direction == "high" else center - value
        if delta <= 0:
            return 0

        return Simulator._clamp_score((delta / (spread * 3.0)) * 100)

    @staticmethod
    def _percentile(values, ratio):
        if len(values) == 1:
            return values[0]

        position = (len(values) - 1) * ratio
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    @staticmethod
    def _clamp_score(value):
        return round(max(0, min(value, 100)))

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
