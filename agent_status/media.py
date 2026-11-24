"""Fit an opened X photo onto the 640x480 laser field."""

import base64
import io
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

for _sdk in ("ble-protocol-sdk", "capability-sdk"):
    _path = str(Path(__file__).resolve().parents[1] / "sdk" / _sdk)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from irisgreen_capability.render import binarize
from visualizer.renderer import FIELD_HEIGHT, FIELD_WIDTH

from .image import MAX_PIXELS
from .protocol import envelope
from .receiver import Rejected

SESSION = "media"
EXPRESSION = "media"

_OPENED = re.compile(r"/status/\d+/photo/\d+")


def is_opened_media(url):
    return bool(_OPENED.search(url or ""))


def adapt_image(encoded):
    """Letterbox one image and light only the pixels above the fixed cut.

    IrisLoop's threshold mode: gray above 127 becomes light, and anything
    darker, including near-black, stays off. The letterbox is black, so it
    stays off too.
    """
    try:
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.width < 1 or im.height < 1 or im.width * im.height > MAX_PIXELS:
                raise ValueError("dimensions")
            gray = im.convert("L")
            scale = min(FIELD_WIDTH / gray.width, FIELD_HEIGHT / gray.height)
            size = (max(1, round(gray.width * scale)), max(1, round(gray.height * scale)))
            fitted = gray.resize(size, Image.Resampling.BOX)
            canvas = Image.new("L", (FIELD_WIDTH, FIELD_HEIGHT), 0)
            canvas.paste(fitted, ((FIELD_WIDTH - size[0]) // 2, (FIELD_HEIGHT - size[1]) // 2))
            mask = binarize(np.asarray(canvas))
    except Exception as exc:
        raise ValueError("image data is not a decodable PNG, JPEG, BMP, or WebP") from exc
    out = Image.fromarray(mask * 255, mode="L")
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    text = base64.b64encode(buf.getvalue()).decode()
    if len(text) > 60000:
        raise ValueError("adapted image is too large")
    return text


def project_media(receiver, agent, body):
    if not isinstance(body, dict):
        raise Rejected(400, "expected an image or clear")
    if body.get("clear") is True and set(body) <= {"clear"}:
        return _clear(receiver, agent)
    if set(body) - {"image_base64"}:
        raise Rejected(400, "expected image_base64")
    encoded = body.get("image_base64")
    if not isinstance(encoded, str) or not encoded:
        raise Rejected(400, "expected image_base64")
    try:
        adapted = adapt_image(encoded)
    except ValueError as exc:
        raise Rejected(400, str(exc)) from exc
    payload = {"intent": "discovery", "expression_id": EXPRESSION,
               "title": "图片", "message": "X", "image_base64": adapted}
    receipt = receiver.receive(envelope("agent.expression", agent, SESSION, payload), agent)
    return {"ok": True, "event_id": receipt["event_id"],
            "expression": {"title": "图片", "message": "X"}}


def dismiss_media(receiver, agent):
    return _clear(receiver, agent)


def _clear(receiver, agent):
    try:
        receiver.receive(envelope(
            "agent.expression.clear", agent, SESSION, {"expression_id": EXPRESSION}), agent)
    except Rejected:
        return {"ok": True, "skipped": True}
    return {"ok": True, "cleared": True}

