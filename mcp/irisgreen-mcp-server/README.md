# IrisGreen MCP Server

Exposes the [capability set](../../docs/capability-spec.md) to AI agents as MCP tools (roadmap V0.4). The server is only the agent-facing interface; BLE, calibration and tracking live in the [Capability SDK](../../sdk/capability-sdk). The machine running it must have a Bluetooth adapter: MCP does not bypass operating-system Bluetooth permissions.

16 tools, named with underscores (`project_point`, `calibration_calibrate`, `tracking_follow`, ...). Results are JSON text plus structured content, with `isError` set on failure. `camera_capture` returns the frame as image content so the agent can see the wall.

## Run

From the repository root, with the dependencies from [requirements.txt](../../requirements.txt):

```text
set PYTHONPATH=sdk/ble-protocol-sdk;sdk/capability-sdk;protocol/python/bleak;algorithms/calibration;algorithms/coordinate-mapping;algorithms/detection;algorithms/tracking;mcp/irisgreen-mcp-server

python -m irisgreen_mcp --simulate                 # simulated device, camera and wall
python -m irisgreen_mcp --camera 0                 # real IrisGreen and USB camera
```

| Option | Meaning |
|---|---|
| `--simulate` | Simulated projector, camera and a moving object; no hardware |
| `--camera N` | OpenCV camera index. Without it there is no camera (projection only) |
| `--data-dir DIR` | Where calibration files and input images live (default `irisgreen_data`). Agent-supplied paths cannot leave it |

## Client configuration

```json
{
  "mcpServers": {
    "irisgreen": {
      "command": "python",
      "args": ["-m", "irisgreen_mcp", "--camera", "0"],
      "cwd": "E:/2027/irisgreen-ai-physical-interface",
      "env": {
        "PYTHONPATH": "sdk/ble-protocol-sdk;sdk/capability-sdk;protocol/python/bleak;algorithms/calibration;algorithms/coordinate-mapping;algorithms/detection;algorithms/tracking;mcp/irisgreen-mcp-server"
      }
    }
  }
}
```

(Use `:` instead of `;` as the path separator on macOS and Linux.)

## What an agent does

1. `device_connect`, `camera_capture` to see the wall.
2. `calibration_calibrate` once, keeping everything still.
3. `camera_capture` with `overlay_field` to see the projectable area, choose a target, then `project_point` (`space: "camera"`), `project_image` (with `region`) or `tracking_start` + `tracking_follow`.
4. `project_clear` before `device_disconnect`.

The server's `instructions` field tells the agent this flow.

Tests: [tests/mcp](../../tests/mcp), including a real stdio subprocess.
