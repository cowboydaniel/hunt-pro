"""Device manager for pairing modular hunting hardware.

This module provides a high-level abstraction for discovering and pairing
Bluetooth-connected field devices such as rangefinders, weather meters, and
shot timers. The implementation focuses on deterministic behaviour that can be
unit tested without real hardware while still modelling realistic constraints
around Bluetooth services, signal strength, and mandatory device metadata.

Phase 6.1 of the roadmap requires an expanded modular device manager that can
pair the key classes of hunting sensors.  The goal of this module is to offer a
clean extension point so that future development (such as vendor plug-ins)
builds on a consistent API.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from importlib import metadata
from typing import Dict, Iterable, Iterator, List, MutableMapping, Optional, Protocol, Set

from logger import LoggableMixin


class DevicePairingError(RuntimeError):
    """Raised when a device cannot be paired."""


class DeviceType(Enum):
    """Supported high-level device categories."""

    RANGEFINDER = "rangefinder"
    WEATHER_METER = "weather_meter"
    SHOT_TIMER = "shot_timer"


class DeviceCapability(Enum):
    """Capabilities that a paired device may expose."""

    DISTANCE_MEASUREMENT = "distance_measurement"
    INCLINATION_MEASUREMENT = "inclination_measurement"
    WIND_SPEED = "wind_speed"
    WIND_DIRECTION = "wind_direction"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    BAROMETRIC_PRESSURE = "barometric_pressure"
    SHOT_DETECTION = "shot_detection"
    SPLIT_TIMES = "split_times"


@dataclass(frozen=True)
class DeviceIdentity:
    """Static identity information exposed by a device during discovery."""

    manufacturer: str
    model: str
    serial_number: str
    firmware: Optional[str] = None

    @property
    def device_id(self) -> str:
        """Unique identifier derived from manufacturer, model, and serial."""

        return f"{self.manufacturer}:{self.model}:{self.serial_number}".lower()


@dataclass
class BluetoothDetails:
    """Connection parameters for a Bluetooth Low Energy device."""

    address: str
    services: List[str] = field(default_factory=list)
    rssi: Optional[int] = None
    protocol: str = "BLE"

    def ensure_service(self, required_services: Iterable[str]) -> None:
        """Validate that the Bluetooth advertisement exposes the services."""

        missing = [svc for svc in required_services if svc not in self.services]
        if missing:
            raise DevicePairingError(
                f"Bluetooth device does not expose required services: {missing}"
            )

    def ensure_signal_strength(self, minimum_rssi: int) -> None:
        """Ensure the received signal strength indicator meets expectations."""

        if self.rssi is None:
            raise DevicePairingError("Bluetooth signal strength (RSSI) unknown")
        if self.rssi < minimum_rssi:
            raise DevicePairingError(
                f"Signal too weak for stable pairing: {self.rssi} < {minimum_rssi}"
            )


@dataclass
class PairingRequest:
    """Data required by adapters to complete a pairing handshake."""

    identity: DeviceIdentity
    connection: BluetoothDetails
    metadata: Dict[str, object] = field(default_factory=dict)

    def require_metadata(self, *keys: str) -> None:
        """Ensure metadata contains the listed keys."""

        missing = [key for key in keys if key not in self.metadata]
        if missing:
            raise DevicePairingError(
                f"Missing metadata required for pairing: {', '.join(missing)}"
            )


@dataclass
class PairedDevice:
    """Representation of a paired hardware device."""

    identity: DeviceIdentity
    device_type: DeviceType
    capabilities: Set[DeviceCapability]
    connection: BluetoothDetails
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def device_id(self) -> str:
        return self.identity.device_id

    @property
    def label(self) -> str:
        firmware = f" v{self.identity.firmware}" if self.identity.firmware else ""
        return f"{self.identity.manufacturer} {self.identity.model}{firmware}"


class DeviceAdapter(Protocol):
    """Adapter protocol that individual device categories must implement."""

    device_type: DeviceType

    def pair(self, request: PairingRequest) -> PairedDevice:
        ...


class BluetoothDeviceAdapter(LoggableMixin):
    """Base class providing helpers for Bluetooth-centric adapters."""

    def __init__(
        self,
        *,
        minimum_rssi: int = -90,
        required_services: Optional[Iterable[str]] = None,
    ):
        super().__init__()
        self._minimum_rssi = minimum_rssi
        self._required_services = list(required_services or [])

    def _validate_connection(self, request: PairingRequest) -> None:
        request.connection.ensure_signal_strength(self._minimum_rssi)
        if self._required_services:
            request.connection.ensure_service(self._required_services)


class RangefinderAdapter(BluetoothDeviceAdapter):
    """Adapter that pairs Bluetooth-enabled rangefinders."""

    device_type = DeviceType.RANGEFINDER

    def __init__(self):
        super().__init__(minimum_rssi=-85, required_services=["huntpro.rangefinder"])

    def pair(self, request: PairingRequest) -> PairedDevice:
        self._validate_connection(request)
        request.require_metadata("max_range")
        max_range = request.metadata["max_range"]
        if not isinstance(max_range, (int, float)) or max_range <= 0:
            raise DevicePairingError("Rangefinder reported invalid max_range value")
        capabilities = {DeviceCapability.DISTANCE_MEASUREMENT}
        if request.metadata.get("supports_inclination", True):
            capabilities.add(DeviceCapability.INCLINATION_MEASUREMENT)
        metadata = dict(request.metadata)
        metadata.setdefault("calibration", "factory")
        return PairedDevice(
            identity=request.identity,
            device_type=self.device_type,
            capabilities=capabilities,
            connection=request.connection,
            metadata=metadata,
        )


class WeatherMeterAdapter(BluetoothDeviceAdapter):
    """Adapter that pairs Bluetooth weather meters."""

    device_type = DeviceType.WEATHER_METER

    SENSOR_TO_CAPABILITY = {
        "temperature": DeviceCapability.TEMPERATURE,
        "humidity": DeviceCapability.HUMIDITY,
        "wind_speed": DeviceCapability.WIND_SPEED,
        "wind_direction": DeviceCapability.WIND_DIRECTION,
        "pressure": DeviceCapability.BAROMETRIC_PRESSURE,
    }

    def __init__(self):
        super().__init__(minimum_rssi=-92, required_services=["huntpro.weather"])

    def pair(self, request: PairingRequest) -> PairedDevice:
        self._validate_connection(request)
        request.require_metadata("sensors")
        sensors = request.metadata["sensors"]
        if not isinstance(sensors, Iterable) or isinstance(sensors, (str, bytes)):
            raise DevicePairingError("Weather meter sensors metadata must be iterable")
        capabilities: Set[DeviceCapability] = set()
        for sensor in sensors:
            capability = self.SENSOR_TO_CAPABILITY.get(str(sensor))
            if capability:
                capabilities.add(capability)
        if not capabilities:
            raise DevicePairingError("Weather meter exposes no supported sensors")
        metadata = dict(request.metadata)
        metadata.setdefault("sample_rate_hz", 1)
        return PairedDevice(
            identity=request.identity,
            device_type=self.device_type,
            capabilities=capabilities,
            connection=request.connection,
            metadata=metadata,
        )


class ShotTimerAdapter(BluetoothDeviceAdapter):
    """Adapter that pairs Bluetooth shot timers used for range practice."""

    device_type = DeviceType.SHOT_TIMER

    def __init__(self):
        super().__init__(minimum_rssi=-88, required_services=["huntpro.shot_timer"])

    def pair(self, request: PairingRequest) -> PairedDevice:
        self._validate_connection(request)
        request.require_metadata("min_split_ms", "sensitivity_db")
        min_split = request.metadata["min_split_ms"]
        sensitivity = request.metadata["sensitivity_db"]
        if not isinstance(min_split, (int, float)) or min_split <= 0:
            raise DevicePairingError("Shot timer minimum split must be a positive number")
        if not isinstance(sensitivity, (int, float)):
            raise DevicePairingError("Shot timer sensitivity must be numeric")
        metadata = dict(request.metadata)
        metadata.setdefault("supports_strings", True)
        capabilities = {DeviceCapability.SHOT_DETECTION}
        if metadata.get("supports_strings"):
            capabilities.add(DeviceCapability.SPLIT_TIMES)
        return PairedDevice(
            identity=request.identity,
            device_type=self.device_type,
            capabilities=capabilities,
            connection=request.connection,
            metadata=metadata,
        )


class DeviceManager(LoggableMixin):
    """Manages the lifecycle of Hunt Pro hardware devices."""

    PLUGIN_ENTRYPOINT_GROUP = "hunt_pro.device_adapters"

    def __init__(self, *, auto_load_plugins: bool = True):
        super().__init__()
        self._adapters: MutableMapping[DeviceType, DeviceAdapter] = {}
        self._paired_devices: MutableMapping[str, PairedDevice] = {}
        self._register_default_adapters()
        if auto_load_plugins:
            self.load_plugin_adapters()

    def _register_default_adapters(self) -> None:
        self.register_adapter(RangefinderAdapter())
        self.register_adapter(WeatherMeterAdapter())
        self.register_adapter(ShotTimerAdapter())

    def register_adapter(self, adapter: DeviceAdapter) -> None:
        if adapter.device_type in self._adapters:
            raise ValueError(f"Adapter already registered for {adapter.device_type.value}")
        self._adapters[adapter.device_type] = adapter
        self.log_info(
            f"Registered adapter for {adapter.device_type.value}",
            device_type=adapter.device_type.value,
        )

    def load_plugin_adapters(self) -> None:
        """Discover and register device adapters provided by plug-ins."""

        for adapter in self._iter_plugin_adapters():
            try:
                self.register_adapter(adapter)
            except ValueError:
                self.log_warning(
                    "Plug-in attempted to register duplicate device adapter",
                    device_type=getattr(adapter.device_type, "value", adapter.device_type),
                )

    def _iter_plugin_adapters(self) -> Iterator[DeviceAdapter]:
        """Yield adapters exposed via Python entry points."""

        try:
            entry_points = metadata.entry_points()
        except Exception as exc:  # pragma: no cover - defensive logging
            self.log_warning(
                "Failed to discover device adapter plug-ins",
                error=repr(exc),
            )
            return

        if hasattr(entry_points, "select"):
            candidates = entry_points.select(group=self.PLUGIN_ENTRYPOINT_GROUP)
        else:  # pragma: no cover - compatibility with older metadata API
            candidates = entry_points.get(self.PLUGIN_ENTRYPOINT_GROUP, [])

        for entry_point in candidates:
            adapter = self._create_adapter_from_entry_point(entry_point)
            if adapter is not None:
                yield adapter

    def _create_adapter_from_entry_point(self, entry_point) -> Optional[DeviceAdapter]:
        try:
            loaded = entry_point.load()
        except Exception as exc:  # pragma: no cover - defensive logging
            self.log_warning(
                "Failed to load device adapter plug-in",
                entry_point=getattr(entry_point, "name", repr(entry_point)),
                error=repr(exc),
            )
            return None

        adapter = self._coerce_adapter(loaded)
        if adapter is None:
            self.log_warning(
                "Plug-in did not return a valid DeviceAdapter",
                entry_point=getattr(entry_point, "name", repr(entry_point)),
                provided_type=type(loaded).__name__,
            )
        return adapter

    def _coerce_adapter(self, candidate) -> Optional[DeviceAdapter]:
        adapter = candidate
        if inspect.isclass(adapter):
            adapter = adapter()
        elif callable(adapter) and not hasattr(adapter, "device_type"):
            adapter = adapter()

        device_type = getattr(adapter, "device_type", None)
        pair_method = getattr(adapter, "pair", None)
        if isinstance(device_type, DeviceType) and callable(pair_method):
            return adapter
        return None

    def pair_bluetooth_device(
        self,
        device_type: DeviceType,
        *,
        identity: DeviceIdentity,
        address: str,
        services: Optional[Iterable[str]] = None,
        rssi: Optional[int] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> PairedDevice:
        adapter = self._adapters.get(device_type)
        if adapter is None:
            raise DevicePairingError(f"No adapter registered for {device_type.value}")
        request = PairingRequest(
            identity=identity,
            connection=BluetoothDetails(
                address=address,
                services=list(services or []),
                rssi=rssi,
            ),
            metadata=dict(metadata or {}),
        )
        paired_device = adapter.pair(request)
        self._paired_devices[paired_device.device_id] = paired_device
        self._logger.log_hardware_event(
            device=paired_device.label,
            event="Paired",
            status="OK",
            device_type=paired_device.device_type.value,
            address=paired_device.connection.address,
        )
        return paired_device

    def get_paired_devices(self, *, device_type: Optional[DeviceType] = None) -> List[PairedDevice]:
        devices = list(self._paired_devices.values())
        if device_type is not None:
            devices = [device for device in devices if device.device_type == device_type]
        return devices

    def get_device(self, device_id: str) -> Optional[PairedDevice]:
        return self._paired_devices.get(device_id.lower())

    def unpair_device(self, device_id: str) -> Optional[PairedDevice]:
        device = self._paired_devices.pop(device_id.lower(), None)
        if device:
            self._logger.log_hardware_event(
                device=device.label,
                event="Unpaired",
                status="OK",
                device_type=device.device_type.value,
                address=device.connection.address,
            )
        return device


__all__ = [
    "DeviceCapability",
    "DeviceIdentity",
    "DeviceManager",
    "DevicePairingError",
    "DeviceType",
    "PairedDevice",
]
