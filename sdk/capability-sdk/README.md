# Capability SDK

Semantic capabilities for AI agents (roadmap V0.3): projection, camera, calibration, tracking and device status, on top of the [BLE Protocol SDK](../ble-protocol-sdk) and the [algorithms](../../algorithms). The full list with schemas is in [docs/capability-spec.md](../../docs/capability-spec.md).

| Module | Role |
|---|---|
| `capabilities` | `build_capabilities`, `CapabilityRegistry`: names, JSON schemas, handlers, validation, error envelope |
| `runtime` | `Runtime`: device, camera, calibration, tracker and the data directory |
| `device` | `IrisDevice`: connect, upload and play a mask, clear |
| `camera` | `Camera` interface, `OpenCvCamera`, `StaticCamera` |
| `tasks` | `project_on_target`: intent to light on the object (V1.0 reference task) |
| `vlm` | `openai_compatible_grounder` for any OpenAI-compatible vision model |
| `sim` | Simulated device, camera and wall for tests and `--simulate` |

```python
import asyncio
from irisgreen_capability import CapabilityRegistry, Runtime, OpenCvCamera

async def main():
    registry = CapabilityRegistry(Runtime(camera=OpenCvCamera(0)))
    await registry.call("device.connect", {})
    await registry.call("calibration.calibrate", {})
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

Tests: [tests/capability](../../tests/capability) and [tests/integration](../../tests/integration).
