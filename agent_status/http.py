"""Authenticated, loopback-only IGASP ingress; PNG output is operator-selected."""

import argparse
import asyncio
import hmac
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from visualizer.renderer.card import CardRenderer
from .page_summary import open_page
from .presentation import AgentPresentation
from .receiver import Receiver, Rejected
from .selection import project_selection

EVENTS = "/api/v1/agent/events"
SNAPSHOT = "/api/v1/agent/snapshot"
PAGE = "/api/v1/page/open"
SELECTION = "/api/v1/selection"
LIMIT = 65536


def make_server(credentials, port=8171, preview=None, priorities=None):
    if not credentials or any(not isinstance(token, str) or not token.isascii() or
                              len(token) < 24 for token in credentials.values()):
        raise ValueError("configure a distinct ASCII bearer token (24+ characters) per agent")
    if len(set(credentials.values())) != len(credentials):
        raise ValueError("tokens must not be shared between agent identities")
    receiver = Receiver()
    presentation = AgentPresentation(receiver, priorities)
    renderer = CardRenderer() if preview else None
    state = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        timeout = 2

        def do_POST(self):
            try:
                if self.path not in (EVENTS, SNAPSHOT, SNAPSHOT + "/read", PAGE, SELECTION):
                    raise Rejected(404, "unknown endpoint")
                auth = self.headers.get("Authorization", "").encode("latin1")
                agent = next((a for a, t in credentials.items()
                              if hmac.compare_digest(auth, f"Bearer {t}".encode())), None)
                if agent is None:
                    raise Rejected(401, "invalid authorization")
                if self.headers.get_content_type() != "application/json":
                    raise Rejected(415, "expected application/json")
                size = int(self.headers.get("Content-Length", "-1"))
                if not 0 < size <= LIMIT or self.headers.get("Transfer-Encoding"):
                    raise Rejected(413, "body must have a bounded Content-Length")
                event = json.loads(self.rfile.read(size).decode("utf8"), parse_constant=_invalid)
                json.dumps(event, ensure_ascii=False).encode("utf-8")
                with state:
                    receiver.admit(agent)
                    if self.path == SNAPSHOT and not (isinstance(event, dict) and event.get("type") == "agent.snapshot"):
                        raise Rejected(400, "expected snapshot event")
                    if self.path == SNAPSHOT + "/read":
                        if not isinstance(event, dict) or not isinstance(event.get("session_id"), str):
                            raise Rejected(400, "expected session_id")
                        data = {"ok": True, "snapshot": receiver.snapshot(agent, event["session_id"])}
                    elif self.path == PAGE:
                        data = open_page(receiver, agent, event)
                    elif self.path == SELECTION:
                        data = project_selection(receiver, agent, event)
                    else:
                        data = receiver.receive(event, agent)
                code = 200
            except Rejected as exc:
                code, data = exc.status, {"ok": False, "error": str(exc)}
            except (ValueError, RecursionError, OverflowError):
                code, data = 400, {"ok": False, "error": "invalid request encoding or value"}
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class LocalServer(ThreadingHTTPServer):
        daemon_threads = True
        last = None
        latest = None

        def service_actions(self):
            with state:
                receiver.prune()
                card = presentation.current()
            tick = int(time.monotonic() * 2) if card and card.pulse else 0
            if renderer and (card, tick) != self.last:
                frame = renderer.frame(card, receiver.clock())
                dest = Path(preview)
                with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as f:
                    tmp = Path(f.name)
                try:
                    Image.fromarray(frame * 255).save(tmp, format="PNG")
                    tmp.replace(dest)
                finally:
                    tmp.unlink(missing_ok=True)
                self.last = card, tick
                self.latest = card, frame

    return LocalServer(("127.0.0.1", port), Handler)


def _invalid(_):
    raise ValueError("not a JSON number")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8171)
    parser.add_argument("--preview", type=Path, required=True, help="local PNG output")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--device", metavar="ADDRESS", help="operator opt-in: overwrite group 1")
    group.add_argument("--simulate-device", action="store_true")
    parser.add_argument("--seconds", type=int, choices=range(1, 301), metavar="1..300",
                        help="optional bounded run; otherwise keep serving until stopped")
    args = parser.parse_args()
    args.preview.parent.mkdir(parents=True, exist_ok=True)
    with make_server(json.loads(os.environ["IGASP_CREDENTIALS"]), args.port, args.preview) as server:
        try:
            if args.device or args.simulate_device:
                from .output import project
                asyncio.run(project(server, args.device, args.simulate_device, args.seconds))
            else:
                server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
