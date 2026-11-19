# IrisGreen MCP Server

Exposes the [capability set](../../docs/capability-spec.md) to AI agents as MCP tools (roadmap V0.4). The server is only the agent-facing interface; BLE and projection live in the [Capability SDK](../../sdk/capability-sdk). The machine running it must have a Bluetooth adapter: MCP does not bypass operating-system Bluetooth permissions.

8 tools, named with underscores: `device_connect`, `device_disconnect`, `device_get_status`, `project_point`, `project_image`, `project_animation`, `project_clear`, `project_status`. Results are JSON text plus structured content, with `isError` set on failure. There is no camera ([ADR 0001](../../docs/adr/0001-remove-camera-pipeline.md)): positions are in projector pixels (640x480).

## Run

From the repository root, with the dependencies from [requirements.txt](../../requirements.txt):

```text
python mcp/irisgreen-mcp-server/launch.py --simulate     # simulated device, no PYTHONPATH needed
python mcp/irisgreen-mcp-server/launch.py                # real IrisGreen over Bluetooth
```

[launch.py](launch.py) puts the repository's package directories on `sys.path` itself. Without it, set `PYTHONPATH=sdk/ble-protocol-sdk;sdk/capability-sdk;protocol/python/bleak;mcp/irisgreen-mcp-server` and run `python -m irisgreen_mcp`.

| Option | Meaning |
|---|---|
| `--simulate` | Simulated projector; no hardware |
| `--address ADDR` | Default BLE address for `device_connect` (or env `IRISGREEN_ADDRESS`). Needed when more than one projector is in range; the agent can still pass its own `address` |
| `--data-dir DIR` | Where input images live (default `irisgreen_data`; `launch.py` uses the repository's). Agent-supplied paths cannot leave it |
| `--no-pre-mirror` | Do not mirror full-field `project_image` content. By default it is mirrored, because a device with mirror 0 shows it horizontally mirrored; use this flag if the device's mirror setting is 1 |

## Client configuration

The repository ships ready-made configs. They run `.venv/Scripts/python.exe` (Windows) with `launch.py` and `--address 20:6E:F1:81:71:62`; edit the address, and the interpreter path on macOS and Linux (`.venv/bin/python`).

| Client | File | Notes |
|---|---|---|
| VS Code (Copilot agent mode) | [.vscode/mcp.json](../../.vscode/mcp.json) | Root key `servers`. Open the folder, then start the server from the MCP: List Servers command or the Chat tools picker |
| Cursor | [.cursor/mcp.json](../../.cursor/mcp.json) | Root key `mcpServers`. Enable `irisgreen` under Settings > MCP |
| WorkBuddy / CodeBuddy | [.mcp.json](../../.mcp.json) | Root key `mcpServers`, project level. Uses `${IRISGREEN_REPO:-E:/2027/irisgreen-ai-physical-interface}`: set `IRISGREEN_REPO` or edit the default if the clone lives elsewhere |

All three launch the same command, so the same tools appear:

```json
{
  "command": "<repo>/.venv/Scripts/python.exe",
  "args": ["<repo>/mcp/irisgreen-mcp-server/launch.py", "--address", "20:6E:F1:81:71:62"]
}
```

Claude Desktop and other clients take the same `command` / `args` under `mcpServers` in their own config file.

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
