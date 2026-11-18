"""IrisGreen MCP server: exposes the capability set to AI agents as MCP tools.

The server is only the agent-facing interface. BLE, calibration and tracking
live in the capability SDK; the process running this server must itself have
access to a BLE adapter (MCP does not get around OS Bluetooth permissions).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from irisgreen_capability import CapabilityRegistry, Runtime

SERVER_NAME = "irisgreen"
SERVER_VERSION = "0.4.0"

INSTRUCTIONS = """\
IrisGreen is a pocket MEMS laser projector. These tools let you put light on a real wall.

Typical flow:
1. device_connect, then camera_capture to see the wall.
2. calibration_calibrate once (keep the camera, projector and wall still); it maps camera pixels to projector pixels.
3. Use camera_capture with overlay_field=true to see the projectable area (orange), pick a target in camera pixels, then project_point (space="camera"), project_image (with region) or tracking_start + tracking_follow.
4. project_clear turns the light off. Always clear before disconnecting.

Every result has ok=true, or ok=false with error.code and error.message. The projector emits at most what its firmware allows; the tools only validate coordinates.
"""

ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"const": False},
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["code", "message"],
        },
    },
    "required": ["ok", "error"],
}


def tool_name(capability_name: str) -> str:
    """`project.point` -> `project_point`: the portable spelling clients accept."""
    return capability_name.replace(".", "_")


def build_tools(registry: CapabilityRegistry) -> list[types.Tool]:
    return [
        types.Tool(
            name=tool_name(cap.name),
            description=cap.description,
            input_schema=cap.input_schema,
            output_schema={"oneOf": [cap.output_schema, ERROR_SCHEMA]},
        )
        for cap in registry
    ]


def to_call_result(result: dict[str, Any]) -> types.CallToolResult:
    """Turn a capability result into MCP content.

    An embedded JPEG is sent as image content (so the agent can see it) rather
    than as a huge base64 string inside the JSON text.
    """
    payload = dict(result)
    content: list[types.TextContent | types.ImageContent] = []
    image = payload.pop("image_base64", None)
    content.append(types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False)))
    if image is not None:
        content.append(types.ImageContent(
            type="image", data=image, mime_type=payload.get("mime_type", "image/jpeg")
        ))
    return types.CallToolResult(
        content=content,
        structured_content=payload,
        is_error=not result.get("ok", False),
    )


def build_server(runtime: Runtime) -> Server:
    registry = CapabilityRegistry(runtime)
    by_tool = {tool_name(name): name for name in registry.names()}
    tools = build_tools(registry)

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        name = by_tool.get(params.name)
        if name is None:
            return to_call_result({
                "ok": False,
                "error": {"code": "invalid_argument", "message": f"unknown tool: {params.name}"},
            })
        return to_call_result(await registry.call(name, params.arguments or {}))

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def make_runtime(args: argparse.Namespace) -> Runtime:
    if args.simulate:
        from irisgreen_capability.sim import make_rig, make_sim_runtime

        runtime, _ = make_sim_runtime(make_rig(moving_object=True), data_dir=args.data_dir, fast=True)
        return runtime

    camera = None
    if args.camera is not None:
        from irisgreen_capability import OpenCvCamera

        camera = OpenCvCamera(args.camera)
    return Runtime(camera=camera, data_dir=args.data_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="irisgreen-mcp", description="IrisGreen MCP server (stdio)"
    )
    parser.add_argument("--simulate", action="store_true",
                        help="use a simulated projector, camera and wall (no hardware)")
    parser.add_argument("--camera", type=int, default=None,
                        help="OpenCV camera index; omit for no camera")
    parser.add_argument("--data-dir", default="irisgreen_data",
                        help="directory for calibration files and input images")
    return parser.parse_args(argv)


async def serve(runtime: Runtime) -> None:
    server = build_server(runtime)
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await runtime.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # stdout carries the protocol, so diagnostics go to stderr.
    print(f"irisgreen-mcp {SERVER_VERSION} ({'simulated' if args.simulate else 'hardware'})",
          file=sys.stderr)
    asyncio.run(serve(make_runtime(args)))
    return 0
