"""Deterministic diagnostics engine for Hunt Pro hardware devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from device_manager import (
    DeviceCapability,
    PairedDevice,
    DeviceType,
)
from logger import get_logger


@dataclass
class SensorMetric:
    """A metric describing a single diagnostic reading."""

    label: str
    value: str
    status: str = "nominal"
    hint: str = ""


@dataclass
class SensorDiagnosticSnapshot:
    """Snapshot of diagnostics for a paired device."""

    device_id: str
    status: str
    signal_quality: int
    battery_level: int
    metrics: List[SensorMetric]
    alerts: List[str]
    calibration_recommended: bool
    last_calibrated: Optional[str]


class SensorDiagnosticsEngine:
    """Produces deterministic diagnostic snapshots for paired devices."""

    _BATTERY_SEQUENCE = [94, 92, 93, 91, 90, 92]
    _SIGNAL_MODULATION = [0, 3, -2, 4, -1]
    _RANGE_OFFSET_SEQUENCE = [0.0, 0.1, -0.2, 0.05, -0.05]
    _INCLINATION_SEQUENCE = [0.1, 0.0, -0.1, 0.2, -0.05]
    _TEMPERATURE_SEQUENCE = [18.4, 18.6, 18.9, 18.3, 18.1]
    _HUMIDITY_SEQUENCE = [52, 53, 51, 50, 54]
    _WIND_SPEED_SEQUENCE = [2.1, 2.4, 2.0, 1.8, 2.2]
    _SHOT_DETECTION_SEQUENCE = [100, 99, 98, 100, 97]
    _SPLIT_VARIANCE_SEQUENCE = [0.03, 0.02, 0.04, 0.01, 0.05]

    def __init__(self) -> None:
        self._device_state: Dict[str, Dict[str, int]] = {}
        self.logger = get_logger()

    def compute_snapshot(self, device: PairedDevice) -> SensorDiagnosticSnapshot:
        """Return the next diagnostic snapshot for a device."""

        state = self._device_state.setdefault(device.device_id, {"tick": -1})
        state["tick"] = (state["tick"] + 1) % 1024
        tick = state["tick"]

        signal_quality = self._modulated_signal(device, tick)
        battery_level = self._cycle_value(self._BATTERY_SEQUENCE, tick)

        metrics = self._build_metrics(device, tick)
        calibration_recommended = self._needs_calibration(device)
        alerts = self._build_alerts(signal_quality, battery_level, calibration_recommended)
        last_calibrated = device.metadata.get("last_calibrated")

        status = "operational"
        if signal_quality < 35:
            status = "degraded"
        if battery_level < 20:
            status = "critical"

        snapshot = SensorDiagnosticSnapshot(
            device_id=device.device_id,
            status=status,
            signal_quality=signal_quality,
            battery_level=battery_level,
            metrics=metrics,
            alerts=alerts,
            calibration_recommended=calibration_recommended,
            last_calibrated=last_calibrated,
        )
        return snapshot

    def _needs_calibration(self, device: PairedDevice) -> bool:
        marker = str(device.metadata.get("calibration", "factory")).lower()
        if "overdue" in marker:
            return True
        if marker in {"factory", "unknown"}:
            return True
        return False

    def _build_metrics(self, device: PairedDevice, tick: int) -> List[SensorMetric]:
        metrics: List[SensorMetric] = []

        if DeviceCapability.DISTANCE_MEASUREMENT in device.capabilities:
            offset = self._cycle_value(self._RANGE_OFFSET_SEQUENCE, tick)
            metrics.append(
                SensorMetric(
                    label="Range offset",
                    value=f"{offset:+.1f} yd",
                    status="ok" if abs(offset) < 0.3 else "warn",
                    hint="Difference between laser range and expected benchmark",
                )
            )
        if DeviceCapability.INCLINATION_MEASUREMENT in device.capabilities:
            drift = self._cycle_value(self._INCLINATION_SEQUENCE, tick)
            metrics.append(
                SensorMetric(
                    label="Inclination drift",
                    value=f"{drift:+.2f}Â°",
                    status="ok" if abs(drift) < 0.5 else "warn",
                    hint="Deviation from leveled reference",
                )
            )
        if DeviceCapability.TEMPERATURE in device.capabilities:
            temp = self._cycle_value(self._TEMPERATURE_SEQUENCE, tick)
            metrics.append(
                SensorMetric(
                    label="Ambient temperature",
                    value=f"{temp:.1f} Â°C",
                    hint="Live reading from weather meter",
                )
            )
        if DeviceCapability.HUMIDITY in device.capabilities:
            humidity = self._cycle_value(self._HUMIDITY_SEQUENCE, tick)
            metrics.append(
                SensorMetric(
                    label="Relative humidity",
                    value=f"{humidity:.0f} %",
                )
            )
        if DeviceCapability.WIND_SPEED in device.capabilities:
            wind = self._cycle_value(self._WIND_SPEED_SEQUENCE, tick)
            metrics.append(
                SensorMetric(
                    label="Wind speed",
                    value=f"{wind:.1f} m/s",
                )
            )
        if DeviceCapability.WIND_DIRECTION in device.capabilities:
            metrics.append(
                SensorMetric(
                    label="Wind direction",
                    value=f"{(tick * 15) % 360:.0f}Â°",
                )
            )
        if DeviceCapability.BAROMETRIC_PRESSURE in device.capabilities:
            metrics.append(
                SensorMetric(
                    label="Barometric pressure",
                    value=f"{1013.2 + (tick % 5) * 0.8:.1f} hPa",
                )
            )
        if DeviceCapability.SHOT_DETECTION in device.capabilities:
            fidelity = self._cycle_value(self._SHOT_DETECTION_SEQUENCE, tick)
            metrics.append(
                SensorMetric(
                    label="Shot detection fidelity",
                    value=f"{fidelity:.0f} %",
                    status="ok" if fidelity >= 95 else "warn",
                )
            )
        if DeviceCapability.SPLIT_TIMES in device.capabilities:
            variance = self._cycle_value(self._SPLIT_VARIANCE_SEQUENCE, tick)
            metrics.append(
                SensorMetric(
                    label="Split variance",
                    value=f"Â±{variance*1000:.0f} ms",
                )
            )

        return metrics

    def _build_alerts(
        self,
        signal_quality: int,
        battery_level: int,
        calibration_recommended: bool,
    ) -> List[str]:
        alerts: List[str] = []
        if signal_quality < 30:
            alerts.append("Bluetooth signal is weak – reposition device for better line of sight.")
        if battery_level < 20:
            alerts.append("Battery level low – charge or replace before departing.")
        if calibration_recommended:
            alerts.append("Calibration recommended to maintain accuracy.")
        return alerts

    def _cycle_value(self, sequence: List[float], tick: int) -> float:
        index = tick % len(sequence)
        return sequence[index]

    def _modulated_signal(self, device: PairedDevice, tick: int) -> int:
        base = self._rssi_to_quality(device.connection.rssi)
        modulation = self._cycle_value(self._SIGNAL_MODULATION, tick)
        return max(0, min(100, int(base + modulation)))

    @staticmethod
    def _rssi_to_quality(rssi: Optional[int]) -> int:
        if rssi is None:
            return 55
        # Map -100..-40 dBm RSSI to roughly 0..100 quality range.
        clamped = max(-100, min(-40, rssi))
        return int((clamped + 100) * (100 / 60))

    def get_calibration_steps(self, device: PairedDevice) -> List[str]:
        """Return recommended calibration steps for a device."""

        if device.device_type == DeviceType.RANGEFINDER:
            return [
                "Secure rangefinder on a tripod aimed at a reflective target.",
                "Trigger three sample measurements at 100 yd benchmark.",
                "Adjust inclination reference to zero using bubble level.",
                "Store calibration profile and verify against secondary target.",
            ]
        if device.device_type == DeviceType.WEATHER_METER:
            return [
                "Place weather meter in shaded, ventilated area.",
                "Run fan calibration cycle for 60 seconds.",
                "Cross-check readings against trusted reference sensor.",
                "Commit calibration and tag device as field-verified.",
            ]
        if device.device_type == DeviceType.SHOT_TIMER:
            return [
                "Power cycle shot timer and reset to factory sensitivity.",
                "Perform dry-fire sequence to tune ambient noise rejection.",
                "Record live fire strings and validate split capture accuracy.",
                "Archive calibration log to Hunt Pro profile.",
            ]
        return ["Review vendor documentation for calibration steps."]


__all__ = [
    "SensorDiagnosticsEngine",
    "SensorDiagnosticSnapshot",
    "SensorMetric",
]
