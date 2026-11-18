# Architecture

IrisGreen separates hardware communication, physical capabilities, algorithms and AI orchestration, so the hardware interface stays stable while algorithms and applications change. The vision of the project is in the [README](../README.md); this page maps it onto the repository.

```text
AI Application / Agent
        |  MCP (stdio)
mcp/irisgreen-mcp-server        V0.4   tools = capabilities
        |
sdk/capability-sdk              V0.3   semantic capabilities, runtime, simulator
   |             \
   |              algorithms/*  V0.5   calibration, coordinate-mapping, detection, tracking
   |
sdk/ble-protocol-sdk            V0.2   commands, image packing, Transport interface
        |  Transport
protocol/python/bleak, protocol/flutter/ble        platform BLE
        |
protocol/gatt/specification     V0.1   the GATT contract
        |
IrisGreen device
```

## Layers and where they live

| Layer | Path | Depends on | Responsibility |
|---|---|---|---|
| GATT profile (V0.1) | [protocol/gatt/specification](../protocol/gatt/specification), [gatt-profile.md](gatt-profile.md) | nothing | What the device exposes: UUIDs, properties, limits. Platform-independent. |
| BLE transports (V0.1/V0.2) | [protocol/python/bleak](../protocol/python/bleak), [protocol/flutter/ble](../protocol/flutter/ble) | GATT profile | One implementation of `Transport` per platform (PC; Android and iOS). |
| BLE Protocol SDK (V0.2) | [sdk/ble-protocol-sdk](../sdk/ble-protocol-sdk) | GATT profile | Command frames, response parsing, 1bpp image packing, file upload, `IrisClient`. No BLE library inside. |
| Algorithms (V0.5) | [algorithms](../algorithms) | numpy, OpenCV | Pure functions and small classes. No BLE, no device. |
| Capability SDK (V0.3) | [sdk/capability-sdk](../sdk/capability-sdk) | BLE SDK, algorithms | Semantic capabilities with JSON schemas, structured errors, runtime state, simulator. |
| MCP server (V0.4) | [mcp/irisgreen-mcp-server](../mcp/irisgreen-mcp-server) | Capability SDK | Agent-facing tools. Never touches BLE itself. |
| Examples / V1.0 | [examples](../examples) | Capability SDK | Vision-to-projection flows. |

Dependencies point downward only. In particular the algorithms know nothing about the device (calibration receives `show_dot` / `grab_frame` callables) and the BLE SDK knows nothing about algorithms.

## Rules the code follows

- **One protocol, two implementations.** The Python and Dart SDKs are checked against the same golden vectors in [tests/cross-platform/protocol-vectors.json](../tests/cross-platform/protocol-vectors.json); the GATT JSON is checked against the Python constants.
- **Transport is the only platform seam.** Everything above `Transport` is identical on every platform.
- **Algorithms are replaceable.** Trackers implement the small `Measurer` protocol; the reference template matcher can be swapped for a stronger one. Image binarization (threshold, Otsu, dither, edges) is an algorithm choice, not part of the protocol.
- **AI-native surface.** Every capability has a stable name, an input and output JSON schema, and returns `ok` or a structured `error.code`. See [capability-spec.md](capability-spec.md).
- **Safety stays on the device.** Laser power and mechanical limits belong to firmware. The SDK only validates coordinates and durations (for example the one-hour playback cap) and never offers a way around the device's own limits.
- **Fail closed on calibration.** A mapping is rejected unless enough dots agree on it and it is geometrically plausible, so a moving scene cannot silently produce a wrong projection.
- **Paths from agents stay inside the data directory.** Image and calibration paths are resolved under one directory and cannot escape it.

## Data flow of the V1.0 task

```text
camera.capture --> VLM grounding --> bbox --> tracking.start
                                                   |
                    +------------------------------+
                    v
 camera frame -> template measurer -> Kalman filter -> aim (lead by upload latency)
                    -> camera->projector mapping -> 640x480 dot -> BLE upload -> light on the object
```

Latency matters because uploading an image takes noticeable time; the Kalman velocity is used to aim slightly ahead, bounded by `max_lead_s` and `max_lead_px` so velocity noise cannot fling the dot away.

## Testing without hardware

[irisgreen_capability.sim](../sdk/capability-sdk/irisgreen_capability/sim.py) provides a simulated device (it speaks the real GATT protocol, reassembles uploads and keeps the projected bitmap), a camera that renders the wall and the green light, and moving objects, all with a known ground-truth mapping. It backs the capability, MCP and integration tests and every example (`--simulate`).

What it cannot show: real BLE behaviour, real optics and exposure, and the V0.1/V0.2 acceptance on Android and iOS hardware. Those still need to be run on devices.

## Environment

`pip install -r requirements.txt` (or use the project's `.venv`), then `python -m pytest` for Python and `flutter test` in `protocol/flutter/ble` for Dart. Run the MCP server with `python -m irisgreen_mcp --simulate` after adding the package directories to `PYTHONPATH`, or install each `pyproject.toml`.
