# Capability SDK

Semantic capabilities for AI agents (roadmap V0.3): device connection and projection, on top of the [BLE Protocol SDK](../ble-protocol-sdk). The full list with schemas is in [docs/capability-spec.md](../../docs/capability-spec.md). The SDK has no camera: see [ADR 0001](../../docs/adr/0001-remove-camera-pipeline.md).

| Module | Role |
|---|---|
| `capabilities` | `build_capabilities`, `CapabilityRegistry`: names, JSON schemas, handlers, validation, error envelope |
| `runtime` | `Runtime`: the device and the data directory |
| `device` | `IrisDevice`: connect, upload and play a mask, clear |
| `render` | Projector field size, single-dot image, gray to 1-bit conversion modes |
| `sim` | Simulated device for tests and `--simulate` |

```python
import asyncio
from irisgreen_capability import CapabilityRegistry, Runtime

async def main():
    registry = CapabilityRegistry(Runtime())
    await registry.call("device.connect", {})
    print(await registry.call("project.point", {"x": 320, "y": 240}))
    await registry.call("project.clear", {})

asyncio.run(main())
```

`registry.call` never raises: it returns `{"ok": true, ...}` or `{"ok": false, "error": {"code", "message"}}`.

Without hardware, use the simulator:

```python
from irisgreen_capability.sim import make_sim_runtime
runtime, rig = make_sim_runtime()
registry = CapabilityRegistry(runtime)
```

The default BLE transport is the Bleak one in [protocol/python/bleak](../../protocol/python/bleak) and must be importable (see `pytest.ini` for the path layout). Pass `Runtime(transport_factory=...)` to use another transport.

Tests: [tests/capability](../../tests/capability).
