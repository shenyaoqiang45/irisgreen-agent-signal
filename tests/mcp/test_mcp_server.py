import asyncio
import base64
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from irisgreen_capability.sim import make_rig, make_sim_runtime
from irisgreen_mcp import build_server, tool_name

ROOT = Path(__file__).parents[2]


def sim_server(tmp_path):
    runtime, rig = make_sim_runtime(make_rig(moving_object=True), data_dir=str(tmp_path))
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
    assert {"device_connect", "project_point", "project_image", "project_clear", "camera_capture",
            "calibration_calibrate", "tracking_follow", "tracking_stop"} <= names
    assert len(names) == 16
    assert all(n.replace("_", "").isalnum() for n in names)  # every client's name rules
    point = next(t for t in listing.tools if t.name == "project_point")
    assert point.input_schema["required"] == ["x", "y"]
    assert point.output_schema["oneOf"][1]["properties"]["ok"] == {"const": False}
    assert "calibration_calibrate" in instructions


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


def test_agent_flow_connect_calibrate_see_project_track(tmp_path):
    server, runtime, rig = sim_server(tmp_path)
    o = rig.world.objects[0]
    bbox = [o.x, o.y, o.width, o.height]

    async def go():
        async with Client(server) as client:
            call = client.call_tool
            connected = await call("device_connect", {})
            calibrated = await call("calibration_calibrate", {"save_path": "wall.json"})
            seen = await call("camera_capture", {"overlay_field": True, "quality": 50})
            dot = await call("project_point", {"x": 320, "y": 240})
            started = await call("tracking_start", {"bbox": bbox})
            followed = await call("tracking_follow", {"duration_s": 2, "max_frames": 30})
            cleared = await call("project_clear", {})
            return connected, calibrated, seen, dot, started, followed, cleared

    connected, calibrated, seen, dot, started, followed, cleared = asyncio.run(go())
    for step in (connected, calibrated, seen, dot, started, followed, cleared):
        assert not step.is_error, step.content
    assert structured(connected)["model"] == "IrisGreen"
    assert structured(calibrated)["stats"]["err_mean"] < 1.0
    assert (tmp_path / "wall.json").exists()

    # the camera frame reaches the agent as an image, not as base64 text
    assert [c.type for c in seen.content] == ["text", "image"]
    assert seen.content[1].mime_type == "image/jpeg"
    assert base64.b64decode(seen.content[1].data)[:2] == b"\xff\xd8"
    assert "image_base64" not in structured(seen)

    assert structured(followed)["aimed_frames"] >= 15
    assert not rig.world.mask.any()  # cleared


def test_stdio_entry_point_serves_the_simulator(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        str(ROOT / p) for p in [
            "sdk/ble-protocol-sdk", "sdk/capability-sdk", "protocol/python/bleak",
            "algorithms/calibration", "algorithms/coordinate-mapping",
            "algorithms/detection", "algorithms/tracking", "mcp/irisgreen-mcp-server",
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
    assert count == 16
    assert not connected.is_error and structured(status)["connected"] is True
