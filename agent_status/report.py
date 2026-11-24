"""Send one message to the IrisGreen receiver from a shell.

python -m agent_status.report --agent copilot --session chat-1 "Tests pass" "Ready to merge"
"""

import argparse
import http.client
import json
import os

from .credentials import resolve
from .protocol import SCHEMA, envelope, send


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("title")
    parser.add_argument("message", nargs="?")
    parser.add_argument("--agent", help="reporting identity (default: IGASP_AGENT)")
    parser.add_argument("--session", default=os.environ.get("IGASP_SESSION", "cli"),
                        help="a new message replaces the previous one in the same session")
    parser.add_argument("--intent", default="milestone",
                        choices=SCHEMA["$defs"]["expression"]["properties"]["intent"]["enum"])
    parser.add_argument("--urgent", action="store_true")
    args = parser.parse_args(argv)
    payload = {"intent": args.intent, "title": args.title}
    if args.message:
        payload["message"] = args.message
    if args.urgent:
        payload["urgency"] = "urgent"
    try:
        agent, token, port = resolve(args.agent)
        result = send(envelope("agent.expression", agent, args.session, payload), token, port)
    except (LookupError, OSError, http.client.HTTPException, ValueError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
