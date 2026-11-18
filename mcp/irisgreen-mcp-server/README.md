# IrisGreen MCP Server

Exposes the [capability set](../../docs/capability-spec.md) to AI agents as MCP tools (roadmap V0.4). The server is only the agent-facing interface; BLE and projection live in the [Capability SDK](../../sdk/capability-sdk). The machine running it must have a Bluetooth adapter: MCP does not bypass operating-system Bluetooth permissions.

7 tools, named with underscores: `device_connect`, `device_disconnect`, `device_get_status`, `project_point`, `project_image`, `project_clear`, `project_status`. Results are JSON text plus structured content, with `isError` set on failure. There is no camera ([ADR 0001](../../docs/adr/0001-remove-camera-pipeline.md)): positions are in projector pixels (640x480).

## Run

From the repository root, with the dependencies from [requirements.txt](../../requirements.txt):

```text
set PYTHONPATH=sdk/ble-protocol-sdk;sdk/capability-sdk;protocol/python/bleak;mcp/irisgreen-mcp-server

python -m irisgreen_mcp --simulate     # simulated device
python -m irisgreen_mcp                # real IrisGreen over Bluetooth
```

| Option | Meaning |
|---|---|
| `--simulate` | Simulated projector; no hardware |
| `--data-dir DIR` | Where input images live (default `irisgreen_data`). Agent-supplied paths cannot leave it |
| `--no-pre-mirror` | Do not mirror full-field `project_image` content. By default it is mirrored, because a device with mirror 0 shows it horizontally mirrored; use this flag if the device's mirror setting is 1 |

## Client configuration

```json
{
  "mcpServers": {
    "irisgreen": {
      "command": "python",
      "args": ["-m", "irisgreen_mcp"],
      "cwd": "E:/2027/irisgreen-ai-physical-interface",
      "env": {
        "PYTHONPATH": "sdk/ble-protocol-sdk;sdk/capability-sdk;protocol/python/bleak;mcp/irisgreen-mcp-server"
      }
    }
  }
}
```

(Use `:` instead of `;` as the path separator on macOS and Linux.)

## What an agent does

1. `device_connect` (with `address` when several projectors are in range).
2. `project_image` (or `project_point`), then `project_status` if it wants to confirm.
3. `project_clear` before `device_disconnect`.

The server's `instructions` field tells the agent this flow.

## Check it on a real device

[verify_mcp_image.py](../../protocol/python/bleak/verify_mcp_image.py) starts this server and acts as the MCP client:

```text
python protocol/python/bleak/verify_mcp_image.py --address 20:6E:F1:81:71:62 --seconds 10
```

Tests: [tests/mcp](../../tests/mcp), including a real stdio subprocess.
