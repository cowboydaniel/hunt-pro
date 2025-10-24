"""Tests for the sensor diagnostics engine."""

from device_manager import (
    BluetoothDetails,
    DeviceCapability,
    DeviceIdentity,
    DeviceType,
    PairedDevice,
)
from sensor_diagnostics import SensorDiagnosticsEngine


def _make_device(
    *,
    device_type: DeviceType,
    capabilities: set,
    calibration: str = "factory",
) -> PairedDevice:
    identity = DeviceIdentity(
        manufacturer="TestCo",
        model=f"Model-{device_type.value}",
        serial_number=f"SN-{device_type.value}",
    )
    connection = BluetoothDetails(address="00:00:00:00:00:00", services=[], rssi=-70)
    metadata = {"calibration": calibration}
    return PairedDevice(
        identity=identity,
        device_type=device_type,
        capabilities=capabilities,
        connection=connection,
        metadata=metadata,
    )


def test_rangefinder_snapshot_flags_calibration_and_reports_metrics():
    engine = SensorDiagnosticsEngine()
    device = _make_device(
        device_type=DeviceType.RANGEFINDER,
        capabilities={
            DeviceCapability.DISTANCE_MEASUREMENT,
            DeviceCapability.INCLINATION_MEASUREMENT,
        },
    )

    snapshot = engine.compute_snapshot(device)

    metric_labels = {metric.label for metric in snapshot.metrics}
    assert "Range offset" in metric_labels
    assert "Inclination drift" in metric_labels
    assert snapshot.calibration_recommended is True
    assert any("Calibration" in alert for alert in snapshot.alerts)


def test_snapshot_cycles_metric_values_over_time():
    engine = SensorDiagnosticsEngine()
    device = _make_device(
        device_type=DeviceType.WEATHER_METER,
        capabilities={
            DeviceCapability.TEMPERATURE,
            DeviceCapability.HUMIDITY,
            DeviceCapability.WIND_SPEED,
        },
    )

    first = engine.compute_snapshot(device)
    second = engine.compute_snapshot(device)

    first_values = [metric.value for metric in first.metrics]
    second_values = [metric.value for metric in second.metrics]
    assert first_values != second_values


def test_calibration_steps_vary_by_device_type():
    engine = SensorDiagnosticsEngine()
    rangefinder = _make_device(
        device_type=DeviceType.RANGEFINDER,
        capabilities={DeviceCapability.DISTANCE_MEASUREMENT},
    )
    shot_timer = _make_device(
        device_type=DeviceType.SHOT_TIMER,
        capabilities={DeviceCapability.SHOT_DETECTION},
        calibration="field_verified",
    )

    range_steps = engine.get_calibration_steps(rangefinder)
    timer_steps = engine.get_calibration_steps(shot_timer)

    assert len(range_steps) >= 3
    assert len(timer_steps) >= 3
    assert range_steps != timer_steps
