import base64
import io
import json
import secrets
from http.client import HTTPConnection
from threading import Thread

import numpy as np
from PIL import Image

from agent_status.http import make_server
from agent_status.media import adapt_image, project_media
from agent_status.page_summary import open_page
from agent_status.presentation import AgentPresentation
from agent_status.receiver import Receiver
from agent_status.selection import project_selection


def _png(width, height, value=255):
    image = Image.new("L", (width, height), value)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _frame(encoded):
    raw = base64.b64decode(adapt_image(encoded))
    with Image.open(io.BytesIO(raw)) as im:
        return np.asarray(im.convert("L"))


def test_near_black_stays_off_and_lighter_pixels_light():
    dark = _frame(_png(80, 8, 40))
    assert dark.sum() == 0
    lit = _frame(_png(80, 8, 200))
    assert lit[220:260].min() == 255
    assert lit[:40].sum() == 0 and lit[-40:].sum() == 0


def test_wide_and_tall_pictures_keep_their_shape_on_the_field():
    wide = _frame(_png(80, 8, 255))
    assert wide.shape == (480, 640)
    assert wide[:40].sum() == 0 and wide[-40:].sum() == 0
    assert wide[220:260].min() == 255
    tall = _frame(_png(8, 80, 255))
    assert tall[:, :40].sum() == 0 and tall[:, -40:].sum() == 0
    assert tall[:, 300:340].min() == 255
    assert _frame(_png(80, 8, 0)).sum() == 0


def test_opened_photo_stays_in_front_until_the_viewer_closes():
    now = [1_700_000_000.0]
    receiver = Receiver(clock=lambda: now[0])
    view = AgentPresentation(receiver)
    home = {
        "url": "https://x.com/home",
        "title": "Home / X",
        "text": "Someone said the launch window is still open for the next round of tests today.",
    }
    photo = {
        "url": "https://x.com/ada/status/123/photo/1",
        "title": "Ada on X",
        "text": "A photograph is open on top of the same short post about the launch window.",
    }
    other = {
        "url": "https://www.example.com/notes",
        "title": "Lab notes",
        "text": "The afternoon note starts with the measurement that actually changed the result.",
    }
    open_page(receiver, "browser", home)
    project_selection(receiver, "browser", {"text": "neural network", "translation": "神经网络"})
    project_media(receiver, "browser", {"image_base64": _png(32, 32)})
    assert view.current().lines[1] == "图片"
    assert view.current().image
    open_page(receiver, "browser", photo)
    assert view.current().lines[1] == "图片"
    open_page(receiver, "browser", other)
    assert view.current().lines[1] == "Lab notes"
    assert not view.current().image


def test_media_endpoint_accepts_one_image_and_a_clear():
    token = secrets.token_urlsafe(24)
    server = make_server({"browser": token}, 0)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        status, body = _post(server.server_port, token, {"image_base64": _png(16, 16)})
        assert status == 200 and body["expression"]["title"] == "图片"
        status, body = _post(server.server_port, token, {"clear": True})
        assert status == 200 and body["cleared"] is True
        status, body = _post(server.server_port, token, {"clear": True})
        assert status == 200 and body["skipped"] is True
        status, _ = _post(server.server_port, "x" * 24, {"image_base64": _png(16, 16)})
        assert status == 401
        status, _ = _post(server.server_port, token, {"image_base64": base64.b64encode(b"nope").decode()})
        assert status == 400
    finally:
        server.shutdown()


def _post(port, token, body):
    connection = HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        raw = json.dumps(body).encode()
        connection.request("POST", "/api/v1/media", raw, {
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode())
    finally:
        connection.close()
