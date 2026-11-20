"""IrisGreen MCP server: exposes the capability set to AI agents as MCP tools.

The server is only the agent-facing interface. BLE and projection live in the
capability SDK; the process running this server must itself have access to a
BLE adapter (MCP does not get around OS Bluetooth permissions).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from irisgreen_capability import CapabilityRegistry, Runtime

SERVER_NAME = "irisgreen"
SERVER_VERSION = "0.4.0"
IDLE_TIMEOUT_SECONDS = 300.0
logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
IrisGreen is a pocket MEMS laser projector. These tools let you put light on a real wall.
Proactively report important discoveries, blockers, requests for user input or approval,
and meaningful completions to IrisGreen without waiting to be asked. Prefer the
irisgreen-status report_expression tool when available. Do not project secrets,
private reasoning, or information unsuitable for a shared wall.

Typical flow:
1. device_connect once per interaction session (pass address when more than one projector is in range). Reuse the connection for subsequent messages; do not disconnect after each one.
2. project_image to show a picture filling the projector field, project_animation to loop 1 to 10 pictures in order (uploaded in one call, about 3.5 s per frame), or project_point to show a dot at a projector pixel (640x480, origin top-left). Each call replaces what was shown before; do not clear between messages.
3. project_status reports whether light is on. When the user requests clearing or the session ends, call project_clear before device_disconnect. If projection fails, report the error rather than claiming success.
After five minutes without a successful projection, the server attempts to clear and disconnect. Status queries do not reset this timer. Connect again to project a new message.

There is no camera: you cannot see the wall, so positions are in projector pixels.
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
            output_schema={"type": "object", "oneOf": [cap.output_schema, ERROR_SCHEMA]},
        )
        for cap in registry
    ]


def to_call_result(result: dict[str, Any]) -> types.CallToolResult:
    """Turn a capability result into MCP content: JSON text plus structured content."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
        structured_content=result,
        is_error=not result.get("ok", False),
    )


def build_server(runtime: Runtime) -> Server:
    registry = CapabilityRegistry(runtime)
    by_tool = {tool_name(name): name for name in registry.names()}
    tools = build_tools(registry)
    lock = asyncio.Lock()
    wake = asyncio.Event()
    deadline: float | None = None
    stopping = False

    async def clear_and_disconnect(reason: str) -> None:
        clear = await registry.call("project.clear", {})
        if not clear.get("ok"):
            logger.error("%s clear failed: %s", reason, clear.get("error"))
        disconnect = await registry.call("device.disconnect", {})
        if not disconnect.get("ok"):
            logger.error("%s disconnect failed: %s", reason, disconnect.get("error"))

    async def watch_idle() -> None:
        nonlocal deadline
        loop = asyncio.get_running_loop()
        while not stopping:
            if deadline is None:
                await wake.wait()
                wake.clear()
                continue
            remaining = deadline - loop.time()
            if remaining > 0:
                try:
                    await asyncio.wait_for(wake.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass
                wake.clear()
                continue
            async with lock:
                if deadline is None or loop.time() < deadline:
                    continue
                deadline = None
                if runtime.device is not None:
                    await clear_and_disconnect("Idle")

    @asynccontextmanager
    async def lifespan(_server):
        nonlocal deadline, stopping
        stopping = False
        if runtime.device is not None and runtime.device.connected:
            deadline = asyncio.get_running_loop().time() + IDLE_TIMEOUT_SECONDS
        task = asyncio.create_task(watch_idle())
        try:
            yield {}
        finally:
            stopping = True
            wake.set()
            await task
            async with lock:
                if runtime.device is not None and runtime.device.connected:
                    await clear_and_disconnect("Shutdown")

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        name = by_tool.get(params.name)
        if name is None:
            return to_call_result({
                "ok": False,
                "error": {"code": "invalid_argument", "message": f"unknown tool: {params.name}"},
            })
        nonlocal deadline
        async with lock:
            result = await registry.call(name, params.arguments or {})
            if result.get("ok"):
                if name == "device.disconnect":
                    deadline = None
                    wake.set()
                elif name in ("project.image", "project.animation", "project.point") or (
                    name == "device.connect" and not result.get("already_connected")
                ):
                    deadline = asyncio.get_running_loop().time() + IDLE_TIMEOUT_SECONDS
                    wake.set()
            return to_call_result(result)

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        instructions=INSTRUCTIONS,
        lifespan=lifespan,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def make_runtime(args: argparse.Namespace) -> Runtime:
    if args.simulate:
        from irisgreen_capability.sim import make_sim_runtime

        runtime, _ = make_sim_runtime(data_dir=args.data_dir, fast=True)
        runtime.mirror_full_field = not args.no_pre_mirror
        runtime.default_address = args.address
        return runtime

    return Runtime(
        data_dir=args.data_dir, mirror_full_field=not args.no_pre_mirror, default_address=args.address
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="irisgreen-mcp", description="IrisGreen MCP server (stdio)"
    )
    parser.add_argument("--simulate", action="store_true",
                        help="use a simulated projector (no hardware)")
    parser.add_argument("--address", default=os.environ.get("IRISGREEN_ADDRESS") or None,
                        help="default BLE address for device_connect (env IRISGREEN_ADDRESS); "
                             "needed when more than one projector is in range")
    parser.add_argument("--no-pre-mirror", action="store_true",
                        help="do not mirror full-field images (use when the device's mirror setting is 1)")
    parser.add_argument("--data-dir", default="irisgreen_data",
                        help="directory for input images; agent-supplied paths cannot leave it")
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
