from ballistics import (  # noqa: E402
    AdaptiveBallisticAdvisor,
    Ammunition,
    BallisticsCalculator,
    EnvironmentalData,
)
from sensor_diagnostics import SensorDiagnosticSnapshot, SensorMetric


def _build_result() -> tuple:
    ammo = Ammunition(
        name="Test 308",
        caliber=".308",
        bullet_weight=168.0,
        muzzle_velocity=820.0,
        ballistic_coefficient=0.47,
    )
    environment = EnvironmentalData(
        temperature=15.0,
        pressure=1013.25,
        humidity=55.0,
        altitude=450.0,
        wind_speed=0.0,
        wind_direction=0.0,
    )
    calculator = BallisticsCalculator()
    # BallisticsCalculator relies on the application logger for additional
    # telemetry hooks that are not required for these unit tests.
    calculator.log_ballistics_calculation = lambda *_, **__: None
    result = calculator.calculate_trajectory(
        ammo=ammo,
        environment=environment,
        zero_distance=100.0,
        max_range=500.0,
        vital_zone_diameter=0.25,
    )
    return calculator, result


def test_adaptive_wind_and_environment_suggestions():
    calculator, result = _build_result()
    advisor = AdaptiveBallisticAdvisor(calculator=calculator)
    advisor.update_baseline_environment(result.environment)
    advisor.clear_sensor_context()

    snapshot = SensorDiagnosticSnapshot(
        device_id="weather-1",
        status="operational",
        signal_quality=80,
        battery_level=90,
        metrics=[
            SensorMetric("Ambient temperature", "8.5 degC"),
            SensorMetric("Relative humidity", "72 %"),
            SensorMetric("Wind speed", "6.4 m/s"),
            SensorMetric("Wind direction", "95 deg"),
            SensorMetric("Barometric pressure", "994.5 hPa"),
        ],
        alerts=[],
        calibration_recommended=False,
        last_calibrated="2024-01-01",
    )

    advisor.ingest_sensor_snapshot(snapshot)
    suggestions = advisor.generate_suggestions(result)

    wind = next(s for s in suggestions if s.focus == "Crosswind")
    assert wind.severity == "warning"
    assert "MOA" in wind.recommendation
    assert "6.4 m/s" in wind.justification

    environment = next(s for s in suggestions if s.focus == "Environment")
    assert "temperature" in environment.justification.lower()
    assert "pressure" in environment.justification.lower()
    assert "drop" in environment.justification.lower()


def test_range_and_inclination_suggestions():
    calculator, result = _build_result()
    advisor = AdaptiveBallisticAdvisor(calculator=calculator)
    advisor.update_baseline_environment(result.environment)
    advisor.clear_sensor_context()

    snapshot = SensorDiagnosticSnapshot(
        device_id="rangefinder-1",
        status="operational",
        signal_quality=78,
        battery_level=88,
        metrics=[
            SensorMetric("Range offset", "+0.6 yd"),
            SensorMetric("Inclination drift", "-0.72 deg"),
        ],
        alerts=[],
        calibration_recommended=True,
        last_calibrated="2023-11-01",
    )

    advisor.ingest_sensor_snapshot(snapshot)
    suggestions = advisor.generate_suggestions(result)

    range_suggestion = next(s for s in suggestions if s.focus == "Range Calibration")
    assert range_suggestion.severity == "warning"
    assert "0.6" in range_suggestion.recommendation

    cant = next(s for s in suggestions if s.focus == "Cant Error")
    assert cant.severity == "warning"
    assert "0.72" in cant.justification
