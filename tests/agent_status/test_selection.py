import json
import secrets
from http.client import HTTPConnection
from threading import Thread

from agent_status.http import make_server
from agent_status.presentation import AgentPresentation
from agent_status.receiver import Receiver
from agent_status.selection import accept, project_selection


def test_only_a_short_english_selection_is_translated():
    assert accept("  neural   network ") == "neural network"
    assert accept("The wall shows one sentence.") == "The wall shows one sentence."
    assert accept("你好") == ""
    assert accept("see 你好") == ""
    assert accept("12345") == ""
    assert accept("one. two. three.") == ""
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


def test_selection_endpoint_requires_the_browser_token():
    token = secrets.token_urlsafe(24)
    server = make_server({"browser": token}, 0)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        status, body = _post(server.server_port, token, {"text": "latency", "translation": "延迟"})
        assert status == 200 and body["expression"]["message"] == "延迟"
        status, body = _post(server.server_port, token, {"text": "see 中文", "translation": "中文"})
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
