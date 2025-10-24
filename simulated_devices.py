"""Helper utilities for provisioning simulated Hunt Pro hardware."""
from __future__ import annotations

from device_manager import DeviceIdentity, DeviceManager, DeviceType


def ensure_simulated_diagnostics_devices(device_manager: DeviceManager) -> None:
    """Ensure a consistent set of simulated devices exist for diagnostics.

    The diagnostics and ballistics modules rely on deterministic simulated
    hardware so that the application can surface meaningful insights even when
    physical devices are not paired. This helper mirrors the bootstrap routine
    used by the diagnostics UI and is intentionally idempotent.
    """

    if device_manager.get_paired_devices():
        return

    device_manager.pair_bluetooth_device(
        DeviceType.RANGEFINDER,
        identity=DeviceIdentity(
            manufacturer="HuntPro",
            model="XR-1200",
            serial_number="SIM-RNG-001",
            firmware="1.2.3",
        ),
        address="00:11:22:33:44:55",
        services=["huntpro.rangefinder"],
        rssi=-68,
        metadata={"max_range": 1200, "calibration": "factory", "simulated": True},
    )

    device_manager.pair_bluetooth_device(
        DeviceType.WEATHER_METER,
        identity=DeviceIdentity(
            manufacturer="SkyWise",
            model="WX-Pro",
            serial_number="SIM-WTH-002",
            firmware="4.1.0",
        ),
        address="00:11:22:33:44:66",
        services=["huntpro.weather"],
        rssi=-72,
        metadata={
            "sensors": ["temperature", "humidity", "wind_speed", "wind_direction"],
            "calibration": "factory",
            "simulated": True,
        },
    )

    device_manager.pair_bluetooth_device(
        DeviceType.SHOT_TIMER,
        identity=DeviceIdentity(
            manufacturer="ShotSense",
            model="Echo",
            serial_number="SIM-SHT-003",
            firmware="2.0.1",
        ),
        address="00:11:22:33:44:77",
        services=["huntpro.shot_timer"],
        rssi=-75,
        metadata={
            "min_split_ms": 60,
            "sensitivity_db": 85,
            "supports_strings": True,
            "calibration": "factory",
            "simulated": True,
        },
    )
