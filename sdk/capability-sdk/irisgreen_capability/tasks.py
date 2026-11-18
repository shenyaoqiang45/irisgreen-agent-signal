"""Reference task: from a spoken-style intent to light on the real object.

This is the vision -> physical loop the whole stack exists for:

    camera frame -> VLM grounding -> calibration -> tracking -> laser aim

An MCP agent composes the same capabilities itself; this packages the
sequence for scripts, examples and tests.
"""

from __future__ import annotations

import base64
from typing import Awaitable, Callable

from irisgreen_detection import GROUND_PROMPT, regions_from_reply

from .capabilities import CapabilityRegistry

# (jpeg bytes, prompt) -> the model's reply text
Grounder = Callable[[bytes, str], Awaitable[str]]


def _failed(stage: str, result: dict) -> dict:
    return {"ok": False, "stage": stage, "error": result["error"]}


async def project_on_target(
    registry: CapabilityRegistry,
    intent: str,
    grounder: Grounder,
    *,
    follow_s: float = 10.0,
    max_frames: int = 300,
) -> dict:
    """Find what `intent` refers to on the wall and keep the laser dot on it.

    Calibrates first if the runtime has no calibration yet. Returns
    ``{"ok": True, "target": {...}, "follow": {...}}`` or
    ``{"ok": False, "stage": <step that failed>, "error": {...}}``.
    """
    runtime = registry.runtime
    if runtime.calibration is None:
        result = await registry.call("calibration.calibrate", {})
        if not result["ok"]:
            return _failed("calibrate", result)

    shot = await registry.call("camera.capture", {"overlay_field": True, "quality": 85})
    if not shot["ok"]:
        return _failed("capture", shot)

    reply = await grounder(base64.b64decode(shot["image_base64"]), GROUND_PROMPT.format(intent=intent))
    try:
        region = regions_from_reply(reply, shot["width"], shot["height"])[0]
    except ValueError as exc:
        return {"ok": False, "stage": "ground",
                "error": {"code": "invalid_argument", "message": str(exc)}}

    x0, y0, x1, y1 = region["bbox"]
    bbox = [x0, y0, x1 - x0, y1 - y0]
    started = await registry.call("tracking.start", {"bbox": bbox})
    if not started["ok"]:
        return _failed("track", started)

    followed = await registry.call(
        "tracking.follow", {"duration_s": follow_s, "max_frames": max_frames}
    )
    if not followed["ok"]:
        return _failed("follow", followed)
    return {
        "ok": True,
        "target": {"label": region["label"], "bbox": bbox},
        "follow": {k: followed[k] for k in ("frames", "aimed_frames", "last")},
    }
