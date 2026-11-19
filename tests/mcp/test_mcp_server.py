import asyncio
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from mcp import Client, StdioServerParameters

from irisgreen_capability.sim import make_sim_runtime
from irisgreen_mcp import build_server, tool_name

ROOT = Path(__file__).parents[2]


def sim_server(tmp_path):
    runtime, rig = make_sim_runtime(data_dir=str(tmp_path))
    return build_server(runtime), runtime, rig


def structured(result):
    return result.structured_content


def test_tool_names_are_portable():
    assert tool_name("project.point") == "project_point"
    assert tool_name("device.get_status") == "device_get_status"


def test_lists_every_capability_with_schemas(tmp_path):
    server, runtime, _ = sim_server(tmp_path)

    async def go():
        async with Client(server) as client:
            return await client.list_tools(), client.instructions

    listing, instructions = asyncio.run(go())
    names = {t.name for t in listing.tools}
    assert names == {
        "device_connect", "device_disconnect", "device_get_status",
        "project_point", "project_image", "project_animation", "project_clear", "project_status",
    }
    assert all(n.replace("_", "").isalnum() for n in names)  # every client's name rules
    point = next(t for t in listing.tools if t.name == "project_point")
    assert point.input_schema["required"] == ["x", "y"]
    assert point.output_schema["oneOf"][1]["properties"]["ok"] == {"const": False}
    # the MCP spec requires an object at the root of every schema; strict clients drop the tool otherwise
    assert all(t.input_schema["type"] == "object" and t.output_schema["type"] == "object"
               for t in listing.tools)
    assert "project_image" in instructions
    assert "do not disconnect after each one" in instructions
    assert "do not clear between messages" in instructions
    assert "Proactively report important discoveries" in instructions


def test_errors_are_flagged_and_structured(tmp_path):
    server, _, _ = sim_server(tmp_path)

    async def go():
        async with Client(server) as client:
            not_connected = await client.call_tool("project_point", {"x": 1, "y": 2})
            bad_args = await client.call_tool("project_point", {"x": "nope", "y": 2})
            unknown = await client.call_tool("does_not_exist", {})
            return not_connected, bad_args, unknown

    not_connected, bad_args, unknown = asyncio.run(go())
    assert not_connected.is_error and structured(not_connected)["error"]["code"] == "not_connected"
    assert bad_args.is_error and structured(bad_args)["error"]["code"] == "invalid_argument"
    assert unknown.is_error and "unknown tool" in structured(unknown)["error"]["message"]
    assert json.loads(not_connected.content[0].text)["ok"] is False


def test_agent_flow_connect_project_image_and_clear(tmp_path):
    server, _, rig = sim_server(tmp_path)
    image = np.zeros((480, 640), np.uint8)
    cv2.rectangle(image, (50, 50), (300, 200), 255, -1)
    cv2.imwrite(str(tmp_path / "a.png"), image)

    async def go():
        async with Client(server) as client:
            call = client.call_tool
            connected = await call("device_connect", {})
            shown = await call("project_image", {"image_path": "a.png"})
            lit = rig.world.mask.copy()
            status = await call("project_status", {})
            dot = await call("project_point", {"x": 320, "y": 240})
            cleared = await call("project_clear", {})
            return connected, shown, lit, status, dot, cleared

    connected, shown, lit, status, dot, cleared = asyncio.run(go())
    for step in (connected, shown, status, dot, cleared):
        assert not step.is_error, step.content
    assert structured(connected)["model"] == "IrisGreen"
    # strict clients validate the result against the output schema, so null/extra fields matter
    assert structured(shown)["lit_pixels"] > 0 and lit.any()
    assert structured(status)["projecting"] is True
    assert not rig.world.mask.any()


def test_launch_script_needs_no_pythonpath(tmp_path):
    """The command the client configs use: a bare interpreter plus launch.py."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "mcp" / "irisgreen-mcp-server" / "launch.py"),
              "--simulate", "--address", "AA:BB", "--data-dir", str(tmp_path)],
        env=env,
    )

    async def go():
        async with Client(params) as client:
            connected = await client.call_tool("device_connect", {})
            return connected

    connected = asyncio.run(asyncio.wait_for(go(), 60))
    assert not connected.is_error and structured(connected)["address"] == "AA:BB"


def test_stdio_entry_point_serves_the_simulator(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        str(ROOT / p) for p in [
            "sdk/ble-protocol-sdk", "sdk/capability-sdk", "protocol/python/bleak",
            "mcp/irisgreen-mcp-server",
        ]
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "irisgreen_mcp", "--simulate", "--data-dir", str(tmp_path)],
        env=env,
    )

    async def go():
        async with Client(params) as client:
            tools = await client.list_tools()
            connected = await client.call_tool("device_connect", {})
            status = await client.call_tool("device_get_status", {})
            return len(tools.tools), connected, status

    count, connected, status = asyncio.run(asyncio.wait_for(go(), 60))
    assert count == 8
    assert not connected.is_error and structured(status)["connected"] is True
