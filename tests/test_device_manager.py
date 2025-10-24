import pytest

import device_manager
from device_manager import (
    AdapterContribution,
    DeviceCapability,
    DeviceIdentity,
    DeviceManager,
    DevicePairingError,
    DeviceType,
    RangefinderAdapter,
)


def make_identity(serial: str = "001") -> DeviceIdentity:
    return DeviceIdentity(
        manufacturer="HuntPro",
        model="FieldUnit",
        serial_number=serial,
        firmware="1.0.0",
    )


def test_pair_rangefinder_assigns_capabilities():
    manager = DeviceManager()
    device = manager.pair_bluetooth_device(
        DeviceType.RANGEFINDER,
        identity=make_identity("RF-123"),
        address="01:02:03:04:05:06",
        rssi=-70,
        services=["huntpro.rangefinder", "battery"],
        metadata={"max_range": 1200, "supports_inclination": True},
    )

    assert device.device_type is DeviceType.RANGEFINDER
    assert DeviceCapability.DISTANCE_MEASUREMENT in device.capabilities
    assert DeviceCapability.INCLINATION_MEASUREMENT in device.capabilities
    assert device.metadata["calibration"] == "factory"


def test_pair_weather_meter_requires_supported_sensors():
    manager = DeviceManager()

    with pytest.raises(DevicePairingError):
        manager.pair_bluetooth_device(
            DeviceType.WEATHER_METER,
            identity=make_identity("WX-1"),
            address="10:11:12:13:14:15",
            rssi=-60,
            services=["huntpro.weather"],
            metadata={"sensors": []},
        )

    device = manager.pair_bluetooth_device(
        DeviceType.WEATHER_METER,
        identity=make_identity("WX-2"),
        address="20:21:22:23:24:25",
        rssi=-61,
        services=["huntpro.weather"],
        metadata={"sensors": ["temperature", "wind_speed"]},
    )

    assert DeviceCapability.TEMPERATURE in device.capabilities
    assert DeviceCapability.WIND_SPEED in device.capabilities
    assert device.metadata["sample_rate_hz"] == 1


def test_pair_shot_timer_tracks_strings_by_default():
    manager = DeviceManager()
    device = manager.pair_bluetooth_device(
        DeviceType.SHOT_TIMER,
        identity=make_identity("ST-007"),
        address="AA:BB:CC:DD:EE:FF",
        rssi=-72,
        services=["huntpro.shot_timer"],
        metadata={"min_split_ms": 60, "sensitivity_db": 95},
    )

    assert DeviceCapability.SHOT_DETECTION in device.capabilities
    assert DeviceCapability.SPLIT_TIMES in device.capabilities
    assert manager.get_device(device.device_id) is device


def test_unpair_device_removes_and_logs():
    manager = DeviceManager()
    device = manager.pair_bluetooth_device(
        DeviceType.RANGEFINDER,
        identity=make_identity("RF-321"),
        address="06:05:04:03:02:01",
        rssi=-65,
        services=["huntpro.rangefinder"],
        metadata={"max_range": 1500},
    )

    removed = manager.unpair_device(device.device_id)
    assert removed is device
    assert manager.get_device(device.device_id) is None


class FakeEntryPoint:
    name = "plugin.shot_timer"

    @staticmethod
    def load():
        return device_manager.ShotTimerAdapter


class FakeEntryPoints:
    def __init__(self, entry_points):
        self._entry_points = entry_points

    def select(self, *, group):
        assert group == DeviceManager.PLUGIN_ENTRYPOINT_GROUP
        return self._entry_points


def fake_entry_points():
    return FakeEntryPoints([FakeEntryPoint()])


def test_load_plugin_adapters_registers_entry_points(monkeypatch):
    monkeypatch.setattr(
        device_manager.metadata,
        "entry_points",
        fake_entry_points,
    )

    manager = DeviceManager(auto_load_plugins=False)
    manager._adapters.pop(DeviceType.SHOT_TIMER)
    manager.load_plugin_adapters()

    assert isinstance(
        manager._adapters[DeviceType.SHOT_TIMER],
        device_manager.ShotTimerAdapter,
    )
def test_load_adapter_plugins_registers_contributions(monkeypatch):
    class VendorRangefinderAdapter(RangefinderAdapter):
        device_type = DeviceType.RANGEFINDER

        def pair(self, request):  # type: ignore[override]
            device = super().pair(request)
            device.metadata["vendor_profile"] = "acme"
            return device

    class VendorPlugin:
        api_version = DeviceManager.PLUGIN_API_VERSION

        def create_adapters(self):
            return [
                AdapterContribution(
                    adapter=VendorRangefinderAdapter(),
                    replace_existing=True,
                )
            ]

    class FakeEntryPoint:
        name = "acme_rangefinder"

        def load(self):
            return VendorPlugin()

    class FakeEntryPoints(list):
        def select(self, *, group):
            if group == DeviceManager.DEFAULT_PLUGIN_GROUP:
                return self
            return FakeEntryPoints()

    def fake_entry_points():
        return FakeEntryPoints([FakeEntryPoint()])

    monkeypatch.setattr("device_manager.metadata", type("MetaModule", (), {"entry_points": staticmethod(fake_entry_points)}))

    manager = DeviceManager(auto_load_plugins=False)
    registered = manager.load_adapter_plugins()

    assert registered == 1

    device = manager.pair_bluetooth_device(
        DeviceType.RANGEFINDER,
        identity=make_identity("RF-777"),
        address="11:22:33:44:55:66",
        rssi=-70,
        services=["huntpro.rangefinder"],
        metadata={"max_range": 1800},
    )

    assert device.metadata["vendor_profile"] == "acme"
