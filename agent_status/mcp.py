"""Agent-facing stdio bridge; unlike the device MCP this exposes no hardware tools."""

import argparse
import asyncio
import http.client
import json
import os

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.runner import serve_loop
from mcp.server.stdio import stdio_server

from .credentials import resolve
from .protocol import SCHEMA, envelope, send

TOOLS = {
    **{f"report_{name}": (f"agent.{name}", name)
       for name in ("profile", "personality", "status", "task", "expression", "snapshot")},
    "clear_status": ("agent.status.clear", None),
    "ack_expression": ("agent.expression.ack", "target"),
    "clear_expression": ("agent.expression.clear", "target"),
    "start_session": ("agent.session.started", None),
    "end_session": ("agent.session.ended", None),
}


def build_server(agent):
    tools = []
    for name, (_, ref) in TOOLS.items():
        props = {"session_id": {"$ref": "#/$defs/id"}}
        if ref == "target":
            props["expression_id"] = {"$ref": "#/$defs/id"}
        elif ref:
            props[ref] = {"$ref": f"#/$defs/{ref}"}
        tools.append(types.Tool(name=name, description=f"IGASP: {name.replace('_', ' ')}.",
                                input_schema={"type": "object", "$defs": SCHEMA["$defs"],
                                              "required": list(props), "properties": props,
                                              "additionalProperties": False}))

    async def listing(ctx, params):
        return types.ListToolsResult(tools=tools)

    async def call(ctx, params):
        try:
            kind, key = TOOLS[params.name]
            args = params.arguments or {}
            session = args["session_id"]
            payload = ({"expression_id": args["expression_id"]} if key == "target" else
                       args[key] if key else {})
            _, token, port = resolve(agent)
            result = await asyncio.to_thread(send, envelope(kind, agent, session, payload), token, port)
        except (LookupError, OSError, http.client.HTTPException, ValueError) as exc:
            result = {"ok": False, "error": str(exc)}
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result))],
                                    structured_content=result, is_error=not result["ok"])

    return Server("irisgreen-agent-status", version="1.0", on_call_tool=call, on_list_tools=listing,
                  instructions="Proactively report important discoveries, blockers, requests for "
                  "user input or approval, and meaningful completions using report_expression; "
                  "do not wait to be asked. An expression may include one image_base64 "
                  "(PNG, JPEG, BMP, or WebP); the receiver fills the field with that image. "
                  "Do not project secrets or sensitive information. "
                  "If reporting fails, tell the user; a receipt does not prove projection. "
                  "Report only your self-declared profile, status and important changes. "
                  "Use a stable session_id and task_id. For persistent messages omit duration_ms and "
                  "ttl_ms; send a new expression to replace the previous message. Do not clear or "
                  "disconnect between reports; the receiver owns the device connection. "
                  "Never guess progress or ETA, report private "
                  "reasoning, or treat a notification acknowledgment as approval to act.")


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default=os.environ.get("IGASP_AGENT"),
                        help="reporting identity (default: IGASP_AGENT). Its token is IGASP_TOKEN, "
                             "or the one python -m agent_status.setup stored")
    agent = parser.parse_args(argv).agent
    if not agent:
        parser.error("pass --agent or set IGASP_AGENT")
    server = build_server(agent)
    async with stdio_server() as (read, write), server.lifespan(server) as state:
        # Handshake era only. Server.run also serves 2026-07-28, and then refuses
        # `initialize` once it has answered server/discover; a client that probes,
        # cannot use the answer and falls back (VS Code Copilot) never connects.
        await serve_loop(server, read, write, lifespan_state=state,
                         init_options=server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
