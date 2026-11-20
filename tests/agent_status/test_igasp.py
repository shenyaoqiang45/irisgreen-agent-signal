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


def test_untimed_notice_holds_until_next_expression_in_session():
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
    before = view.current()
    r.receive(envelope("agent.status", "a", "s", {"state": "awaiting_approval"}), "a")
    r.receive(envelope("agent.task", "a", "s", {"task_id": "t", "title": "Task", "status": "running"}), "a")
    assert view.current() == before
    snapshot = r.snapshot("a", "s")
    assert snapshot["payload"]["expressions"][0]["expression"]["title"] == "Second"
    r.receive(snapshot, "a")
    assert view.current().lines[1] == "Second"
    r.receive(envelope("agent.expression.clear", "a", "s", {
        "expression_id": snapshot["payload"]["expressions"][0]["expression"]["expression_id"]}), "a")
    assert view.current().lines[1] == "awaiting_approval"


def test_live_output_reuses_connection_and_replaces_without_clearing(tmp_path, monkeypatch):
    from agent_status import output

    calls = []

    class Device:
        def __init__(self, **kwargs):
            pass

        async def connect(self):
            calls.append(("connect",))
            return {"ok": True}

        async def push_frame(self, frame, seconds):
            calls.append(("show", int(frame.sum()), seconds))
            return {"ok": True}

        async def clear(self):
            calls.append(("clear",))
            return {"ok": True}

        async def disconnect(self):
            calls.append(("disconnect",))
            return {"ok": True}

    monkeypatch.setattr(output, "McpDeviceAdapter", Device)
    token = secrets.token_urlsafe(32)

    async def run(server):
        task = asyncio.create_task(output.project(server, "device", True, None))

        async def wait_for(predicate):
            for _ in range(100):
                if predicate():
                    return
                await asyncio.sleep(.05)
            pytest.fail(f"timed out waiting for output: {calls}")

        try:
            await wait_for(lambda: calls == [("connect",)])
            for title in ("First", "Second"):
                event = envelope("agent.expression", "a", "s", {"intent": "idea", "title": title})
                assert (await asyncio.to_thread(send, event, token, server.server_port))["ok"]
                expected = 1 if title == "First" else 2
                await wait_for(lambda: len([c for c in calls if c[0] == "show"]) == expected)
                if title == "First":
                    status = envelope("agent.status", "a", "s", {"state": "working"})
                    assert (await asyncio.to_thread(send, status, token, server.server_port))["ok"]
                    await asyncio.sleep(.5)
                    assert len([c for c in calls if c[0] == "show"]) == 1
            assert [c[0] for c in calls] == ["connect", "show", "show"]
            assert all(c[2] == 3600 for c in calls if c[0] == "show")
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert [c[0] for c in calls] == ["connect", "show", "show", "clear", "disconnect"]

    with make_server({"a": token}, 0, tmp_path / "out.png") as server:
        asyncio.run(run(server))


def test_card_layout_spreads_content_and_keeps_masks_inside_field(monkeypatch):
    from visualizer.core.presentation import Card
    from visualizer.renderer import card as card_module

    calls = []
    original = card_module.blit

    def checked_blit(frame, mask, x, y, **kwargs):
        left, top = x - mask.shape[1] // 2, y - mask.shape[0] // 2
        assert left >= 0 and top >= 0
        assert left + mask.shape[1] <= frame.shape[1]
        assert top + mask.shape[0] <= frame.shape[0]
        calls.append((left, top, mask.shape, y))
        original(frame, mask, x, y, **kwargs)

    monkeypatch.setattr(card_module, "blit", checked_blit)
    renderer = card_module.CardRenderer()
    card = Card(("agent / session", "Important update", "warning", "Please review the change."), 1, 1)
    frame = renderer.frame(card, 0)
    assert frame.shape == (480, 640) and frame.any()
    assert calls[1][0] < frame.shape[1] // 4
    assert calls[-1][1] - calls[0][1] > 150
    assert all(calls[i][1] + calls[i][2][0] < calls[i + 1][1] for i in range(len(calls) - 1))
    assert len({calls[i + 1][3] - calls[i][3] for i in range(len(calls) - 1)}) == 1


def test_card_wraps_long_text_and_marks_extreme_overflow():
    from visualizer.core.presentation import Card
    from visualizer.renderer.card import CardRenderer

    renderer = CardRenderer()
    message = "A" * 160
    groups = renderer._content(("Title", "warning", message))
    assert "".join(row[0] for row in groups[-1]) == message
    assert len(groups[-1]) > 1
    overflow = renderer._content(("W" * 160,) * 4)
    assert overflow[-1][-1][0].endswith("…")
    assert renderer.frame(Card(("agent", "A" * 160, "B" * 160, "C" * 160, "D" * 160), 1, 1), 0).any()


def test_expression_uses_uniform_font_size(monkeypatch):
    from visualizer.renderer.card import CardRenderer

    renderer = CardRenderer()
    if not renderer.supports_cjk:
        pytest.skip("requires a CJK font")
    title = "我发现了一个需要注意的问题"
    message = "当多个代理同时上报时，需要使用同一个接收器，避免设备连接发生冲突。"
    receiver = Receiver()
    presentation = AgentPresentation(receiver)
    receiver.receive(envelope("agent.expression", "copilot", "this-chat",
                              {"title": title, "intent": "warning", "message": message}), "copilot")
    card = presentation.current()
    groups = renderer._content(card.lines[1:], include_source=True)
    assert len(groups[-1]) == 3
    assert "".join(row[0] for row in groups[-1]) == message
    assert {row[1] for group in groups for row in group} == {48}

    sizes = {}
    original = renderer._label
    def label(text, size):
        sizes[text] = size
        return original(text, size)
    monkeypatch.setattr(renderer, "_label", label)
    renderer.frame(card, 0)
    assert set(sizes.values()) == {48}


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
                    assert "Proactively report important discoveries" in client.instructions
                    assert "a receipt does not prove projection" in client.instructions
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
