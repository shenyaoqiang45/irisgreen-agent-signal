import json
import secrets
from http.client import HTTPConnection
from threading import Thread

from agent_status.http import make_server
from agent_status.page_summary import open_page
from agent_status.presentation import AgentPresentation
from agent_status.protocol import envelope
from agent_status.receiver import Receiver
from agent_status.selection import accept, project_selection


def test_a_short_phrase_in_any_language_can_be_translated():
    assert accept("  neural   network ") == "neural network"
    assert accept("The wall shows one sentence.") == "The wall shows one sentence."
    assert accept("bonjour") == "bonjour"
    assert accept("こんにちは") == "こんにちは"
    assert accept("안녕하세요") == "안녕하세요"
    assert accept("Привет") == "Привет"
    assert accept("你好") == "你好"
    assert accept("12345") == ""
    assert accept("one. two. three.") == ""
    assert accept("一つ。二つ。") == ""
    assert accept("word " * 40) == ""


def test_a_new_selection_replaces_the_previous_gloss_and_then_clears():
    now = [1_700_000_000.0]
    receiver = Receiver(clock=lambda: now[0])
    view = AgentPresentation(receiver)
    first = project_selection(receiver, "browser", {"text": "hello", "translation": "你好"})
    assert first["expression"] == {"title": "hello", "message": "你好"}
    assert view.current().lines[1] == "hello"
    assert view.current().lines[3] == "你好"
    project_selection(receiver, "browser", {"text": "network", "translation": "网络"})
    assert view.current().lines[3] == "网络"
    assert len(receiver.snapshot("browser", "selection")["payload"]["expressions"]) == 1
    assert project_selection(receiver, "browser", {"text": "你好", "translation": "你好"})["skipped"]
    now[0] += 61
    assert view.current() is None


def test_gloss_stays_ahead_of_a_later_page_until_the_hold_ends():
    now = [1_700_000_000.0]
    receiver = Receiver(clock=lambda: now[0])
    view = AgentPresentation(receiver)
    project_selection(receiver, "browser", {"text": "neural network", "translation": "神经网络"})
    open_page(receiver, "browser", {
        "url": "https://x.com/home",
        "title": "Home / X",
        "text": "Someone said the launch window is still open for the next round of tests today.",
    })
    assert view.current().lines[1] == "neural network"
    approval = envelope(
        "agent.expression", "cursor", "s",
        {"intent": "approval_required", "title": "Approve", "message": "Need you"})
    receiver.receive(approval, "cursor")
    assert view.current().lines[1] == "Approve"
    receiver.receive(envelope(
        "agent.expression.clear", "cursor", "s",
        {"expression_id": approval["event_id"]}), "cursor")
    assert view.current().lines[1] == "neural network"
    assert view.current().lines[3] == "神经网络"
    now[0] += 61
    assert view.current().lines[1] == "Home / X"


def test_another_page_replaces_the_gloss_without_waiting_out_the_hold():
    now = [1_700_000_000.0]
    receiver = Receiver(clock=lambda: now[0])
    view = AgentPresentation(receiver)
    home = {
        "url": "https://x.com/home",
        "title": "Home / X",
        "text": "Someone said the launch window is still open for the next round of tests today.",
    }
    open_page(receiver, "browser", home)
    project_selection(receiver, "browser", {"text": "neural network", "translation": "神经网络"})
    open_page(receiver, "browser", dict(home, text="Someone said the launch window moved, but this is still the same page."))
    assert view.current().lines[1] == "neural network"
    open_page(receiver, "browser", {
        "url": "https://www.example.com/notes",
        "title": "Lab notes",
        "text": "The afternoon note starts with the measurement that actually changed the result.",
    })
    assert view.current().lines[1] == "Lab notes"
    assert "measurement" in view.current().lines[3]


def test_selection_endpoint_requires_the_browser_token():
    token = secrets.token_urlsafe(24)
    server = make_server({"browser": token}, 0)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        status, body = _post(server.server_port, token, {"text": "latency", "translation": "延迟"})
        assert status == 200 and body["expression"]["message"] == "延迟"
        status, body = _post(server.server_port, token, {"text": "こんにちは", "translation": "你好"})
        assert status == 200 and body["expression"]["message"] == "你好"
        status, body = _post(server.server_port, token, {"text": "你好", "translation": "你好"})
        assert status == 200 and body["skipped"]
        status, _ = _post(server.server_port, "x" * 24, {"text": "hello", "translation": "你好"})
        assert status == 401
    finally:
        server.shutdown()


def _post(port, token, body):
    connection = HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        raw = json.dumps(body).encode()
        connection.request("POST", "/api/v1/selection", raw, {
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode())
    finally:
        connection.close()
