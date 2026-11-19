import asyncio
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

import pytest
from mcp import Client, StdioServerParameters
from PIL import Image

from agent_status.http import make_server
from agent_status.mcp import send
from agent_status.presentation import AgentPresentation
from agent_status.protocol import envelope, validator
from agent_status.receiver import Receiver, Rejected

ROOT = Path(__file__).resolve().parents[2]


def test_snapshot_recovery_isolation_and_idempotence():
    event = json.loads((ROOT / "protocol/igasp/example.snapshot.json").read_text())
    r = Receiver()
    view = AgentPresentation(r)
    bus = []
    r.bus.subscribe("agent.", bus.append)
    r.receive(event, "codex")
    assert r.receive(event, "codex")["duplicate"] and len(bus) == 1
    assert view.current().lines[1] == "Review renderer"
    assert "%" not in "".join(view.current().lines)
    r.receive(envelope("agent.status", "codex", "another", {"mood": "curious"}), "codex")
    snapshot = r.snapshot("codex", "session_001")
    assert snapshot["payload"] == event["payload"]
    assert r.snapshot("codex", "another")["payload"]["profile"] == event["payload"]["profile"]
    with pytest.raises(Rejected, match="identity"):
        r.receive(event, "cursor")
    with pytest.raises(Rejected, match="already used"):
        r.receive(dict(event, session_id="other"), "codex")
    r.receive(envelope("agent.session.ended", "codex", "session_001", {}), "codex")
    assert view.current().lines[3] == "curious"
    r.receive(snapshot, "codex")
    assert view.current().lines[1] == "Review renderer"


def test_display_and_validity_expire_independently():
    now = [datetime.now(timezone.utc).timestamp()]
    r = Receiver(clock=lambda: now[0])
    v = AgentPresentation(r)
    def report(kind, payload, agent="a"):
        event = envelope("agent." + kind, agent, "s", payload)
        event["timestamp"] = datetime.fromtimestamp(now[0], timezone.utc).isoformat()
        return r.receive(event, agent)["event_id"]
    report("status", {"state": "thinking"})
    report("status", {"mood": "focused"})
    eid = report("expression", {"intent": "idea", "title": "Note", "ttl_ms": 6000, "duration_ms": 1000}, "b")
    assert v.current().lines[1] == "Note"
    now[0] += 2
    assert v.current().lines[1:4] == ("thinking", "", "focused")
    snapshot = r.snapshot("b", "s")
    r.receive(snapshot, "b")
    assert v.current().lines[1] == "thinking"
    report("expression.ack", {"expression_id": eid}, "b")
    report("expression", {"intent": "warning", "title": "Check", "urgency": "urgent", "ttl_ms": 100}, "b")
    assert v.current().priority == 0
    now[0] += 1
    assert not r.snapshot("b", "s")["payload"]["expressions"]
    assert v.current().lines[1] == "thinking"


def test_untimed_notice_holds_until_next_accepted_report_in_session():
    now = [datetime.now(timezone.utc).timestamp()]
    r = Receiver(clock=lambda: now[0])
    view = AgentPresentation(r)
    first = envelope("agent.expression", "a", "s", {"intent": "idea", "title": "First", "urgency": "urgent"})
    r.receive(first, "a")
    now[0] += 86400
    r.receive(first, "a")
    r.receive(envelope("agent.status", "a", "other", {"state": "idle"}), "a")
    assert view.current().lines[1] == "First"
    r.receive(envelope("agent.expression", "a", "s", {"intent": "idea", "title": "Second"}), "a")
    assert view.current().lines[1] == "Second"
    assert len(r.snapshot("a", "s")["payload"]["expressions"]) == 1
    r.receive(envelope("agent.status", "a", "s", {"state": "working"}), "a")
    assert view.current().lines[1] == "working"
    assert not r.snapshot("a", "s")["payload"]["expressions"]


@pytest.mark.parametrize("kind,payload", [
    ("task", {"task_id": "a", "title": "T", "status": "running", "progress": 101}),
    ("expression", {"intent": "discovery", "title": "T", "image_path": "ignored.png"}),
    ("status", {"state": "happy"}), ("personality", {"source": "inferred"}),
])
def test_bad_event_never_mutates_session(kind, payload):
    r = Receiver()
    with pytest.raises(Rejected):
        r.receive(envelope("agent." + kind, "a", "s", payload), "a")
    assert not r.sessions


def test_stdio_and_http_share_authenticated_receiver(tmp_path):
    token = secrets.token_urlsafe(32)
    dest = tmp_path / "out.png"
    with make_server({"a": token}, 0, dest) as server:
        port = server.server_port
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": .05})
        worker.start()
        try:
            event = envelope("agent.status", "a", "s", {"state": "working"})
            assert not send(event, "wrong", port)["ok"]
            assert send(event, token, port)["ok"]
            async def go():
                params = StdioServerParameters(command=sys.executable,
                    args=[str(ROOT / "mcp/irisgreen-agent-status/launch.py")],
                    env={"IGASP_AGENT": "a", "IGASP_TOKEN": token, "IGASP_PORT": str(port)})
                async with Client(params) as client:
                    names = {t.name for t in (await client.list_tools()).tools}
                    assert "report_snapshot" in names and "project_image" not in names
                    result = await client.call_tool("report_status", {"session_id": "s", "status": {"mood": "focused"}})
                    assert not result.is_error, result.content
            asyncio.run(go())
        finally:
            server.shutdown()
            worker.join()
        assert server.latest[0].lines[1:4] == ("working", "", "focused")
        assert Image.open(dest).size == (640, 480) and server.latest[1].any()


def test_date_and_rate_limit():
    event = envelope("agent.session.started", "a", "s", {})
    assert not validator.is_valid(dict(event, timestamp="2026-02-31T12:00:00Z"))
    r = Receiver()
    for _ in range(30):
        r.admit("a")
    with pytest.raises(Rejected) as exc:
        r.admit("a")
    assert exc.value.status == 429
    r.admit("b")
