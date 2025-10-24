# Device Adapter Plug-in Protocol

Hunt Pro exposes an extension system that allows third-party hardware vendors to
contribute pairing logic for their devices without modifying the core
application. Adapters are discovered at runtime through Python entry points so a
vendor can ship an installable Python package that registers with Hunt Pro when
installed in the same environment.

## Entry point definition

Publish an entry point named `hunt_pro.device_adapters` from your package and
return an object that follows the `DeviceAdapterPlugin` protocol:

```toml
[project.entry-points."hunt_pro.device_adapters"]
acme_rangefinder = "acme_hunt.adapters:Plugin"
```

The entry point must resolve to either an instance of, or a callable that
returns, an object with the following structure:

```python
from dataclasses import dataclass
from typing import Iterable

from device_manager import (
    AdapterContribution,
    BluetoothDeviceAdapter,
    DeviceAdapterPlugin,
    DeviceType,
)

class Plugin(DeviceAdapterPlugin):
    api_version = "1.0"

    def create_adapters(self) -> Iterable[AdapterContribution]:
        return [AdapterContribution(adapter=AcmeRangefinderAdapter(), replace_existing=True)]

class AcmeRangefinderAdapter(BluetoothDeviceAdapter):
    device_type = DeviceType.RANGEFINDER

    def pair(self, request):
        # Perform any vendor-specific validation before returning a PairedDevice
        return super().pair(request)
```

Key requirements:

* `api_version` **must** match the version exposed by `DeviceManager.PLUGIN_API_VERSION`.
* `create_adapters()` must return one or more `AdapterContribution` objects.
  * Use `replace_existing=True` when the adapter should override the built-in
    Hunt Pro adapter for the same `DeviceType`.
  * Returning a bare adapter instance is also supported and is treated as
    `replace_existing=False`.
* Each adapter must implement the `DeviceAdapter` protocol (`device_type` and a
  `pair()` method returning a `PairedDevice`).

## Runtime behaviour

`DeviceManager` automatically discovers adapters via entry points on
initialisation. Plug-ins that target an unknown API version are skipped with a
warning to avoid runtime incompatibilities. Any errors raised by a plug-in are
captured and logged so that misbehaving third-party packages do not impact core
functionality.

To manually trigger discovery (for example during tests or on-demand reloads),
call:

```python
from device_manager import DeviceManager

manager = DeviceManager(auto_load_plugins=False)
manager.load_adapter_plugins()
```

After registration, devices can be paired using `DeviceManager` just like
built-in hardware support.
