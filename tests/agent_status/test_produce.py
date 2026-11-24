import json
import secrets
from http.client import HTTPConnection
from threading import Thread

from agent_status.http import make_server
from agent_status.page_summary import open_page
from agent_status.presentation import AgentPresentation
from agent_status.produce import identify, project_produce
from agent_status.receiver import Receiver


def test_a_clicked_label_names_the_produce_and_its_calories():
    assert identify("照片 alt=红苹果") == ("苹果", 52)
    assert identify("https://example.com/images/banana.jpg") == ("香蕉", 89)
    assert identify("菠萝 pineapple") == ("菠萝", 50)
    assert identify("樱桃") == ("樱桃", 63)
    assert identify("自行车") is None
    assert identify("") is None


def test_produce_stays_in_front_of_the_page_until_the_address_changes():
    now = [1_700_000_000.0]
    receiver = Receiver(clock=lambda: now[0])
    view = AgentPresentation(receiver)
    home = {
        "url": "https://example.com/market",
        "title": "Market",
        "text": "The stall lists fruit by the piece and keeps the prices on a handwritten card.",
    }
    open_page(receiver, "browser", home)
    shown = project_produce(receiver, "browser", {"hint": "figcaption: 草莓"})
    assert shown["expression"] == {"title": "草莓", "message": "32 千卡/100克"}
    assert view.current().lines[1] == "草莓"
    open_page(receiver, "browser", {
        "url": "https://example.com/other",
        "title": "Other stall",
        "text": "The next stall sells jars and keeps its sign above the counter.",
    })
    assert view.current().lines[1] == "Other stall"


def test_produce_endpoint_skips_an_unknown_picture():
    token = secrets.token_urlsafe(24)
    server = make_server({"browser": token}, 0)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        status, body = _post(server.server_port, token, {"hint": "carrot"})
        assert status == 200 and body["expression"]["title"] == "胡萝卜"
        status, body = _post(server.server_port, token, {"hint": "a red bicycle"})
        assert status == 200 and body["skipped"] is True
        status, _ = _post(server.server_port, "x" * 24, {"hint": "apple"})
        assert status == 401
    finally:
        server.shutdown()


def _post(port, token, body):
    connection = HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        raw = json.dumps(body).encode()
        connection.request("POST", "/api/v1/produce", raw, {
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode())
    finally:
        connection.close()
