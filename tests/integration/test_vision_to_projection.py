"""V1.0: an agent-style task from camera frame to light on the real object."""

import asyncio
import base64
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import cv2
import numpy as np
import pytest

from irisgreen_ble import image_pack
from irisgreen_capability import (
    CapabilityRegistry,
    openai_compatible_grounder,
    project_on_target,
)
from irisgreen_capability.sim import make_rig, make_sim_runtime
from irisgreen_capability.vlm import VlmError

ROOT = Path(__file__).parents[2]


def boxed_reply(rig, label="patch", margin=0.0):
    """What a VLM would answer: the object's box in 0-1000 normalized coordinates."""
    o = rig.world.objects[0]
    w, h = rig.world.camera_size
    box = [(o.x - margin) / w * 1000, (o.y - margin) / h * 1000,
           (o.x + o.width + margin) / w * 1000, (o.y + o.height + margin) / h * 1000]
    return json.dumps([{"label": label, "bbox_2d": box}])


@pytest.fixture
def world(tmp_path):
    runtime, rig = make_sim_runtime(make_rig(moving_object=True), data_dir=str(tmp_path))
    return CapabilityRegistry(runtime), runtime, rig


def test_intent_to_light_on_the_object(world):
    registry, runtime, rig = world
    seen = {}

    async def grounder(jpeg: bytes, prompt: str) -> str:
        seen["jpeg"], seen["prompt"] = jpeg, prompt
        return "Sure!\n```json\n" + boxed_reply(rig, "the red-bordered patch", margin=2) + "\n```"

    async def go():
        assert (await registry.call("device.connect", {}))["ok"]
        outcome = await project_on_target(
            registry, "highlight the red-bordered patch", grounder, follow_s=3, max_frames=60
        )
        return outcome

    outcome = asyncio.run(go())
    assert outcome["ok"], outcome
    assert outcome["target"]["label"] == "the red-bordered patch"
    assert outcome["follow"]["aimed_frames"] >= outcome["follow"]["frames"] - 3

    # the model saw a real camera frame (JPEG) and a prompt carrying the intent
    assert seen["jpeg"][:2] == b"\xff\xd8"
    assert "highlight the red-bordered patch" in seen["prompt"] and "orange" in seen["prompt"]
    # it calibrated by itself, and the light really is on the object now
    assert runtime.calibration is not None
    lit, true = rig.world.lit_camera_centroid(), rig.world.objects[0].center
    assert np.hypot(lit[0] - true[0], lit[1] - true[1]) < 12.0
    assert rig.world.playing
    # images went over the BLE protocol as complete 1bpp streams
    assert rig.world.uploads and all(
        name == "1_1.bmp" and size == image_pack.STREAM_BYTES for name, size in rig.world.uploads
    )


@pytest.mark.parametrize("reply, stage", [
    ("I cannot see any such object.", "ground"),
    ('[{"label": "x", "bbox_2d": [500, 500, 100, 100]}]', "ground"),
])
def test_unusable_model_reply_stops_before_any_light(world, reply, stage):
    registry, _, rig = world

    async def grounder(jpeg, prompt):
        return reply

    async def go():
        await registry.call("device.connect", {})
        uploads_before = len(rig.world.uploads)
        outcome = await project_on_target(registry, "anything", grounder)
        return outcome, uploads_before

    outcome, before = asyncio.run(go())
    assert outcome["ok"] is False and outcome["stage"] == stage
    # only calibration dots were projected; the target itself never was
    assert len(rig.world.uploads) > before and not registry.runtime.tracker.active


def test_task_reports_the_stage_that_failed(world):
    registry, _, _ = world

    async def grounder(jpeg, prompt):
        raise AssertionError("must not be reached")

    outcome = asyncio.run(project_on_target(registry, "x", grounder))  # no device connected
    assert outcome["ok"] is False and outcome["stage"] == "calibrate"
    assert outcome["error"]["code"] == "not_connected"


def test_target_lost_during_follow_is_reported(world):
    registry, _, rig = world
    state = {"armed": False, "grabs": 0}
    original_grab = rig.camera.grab

    async def grab_then_vanish():
        frame = await original_grab()
        if state["armed"]:
            state["grabs"] += 1
            if state["grabs"] == 5:  # tracking.start + a few good frames, then it is gone
                rig.world.objects.clear()
        return frame

    rig.camera.grab = grab_then_vanish

    async def grounder(jpeg, prompt):
        state["armed"] = True
        return boxed_reply(rig)

    async def go():
        await registry.call("device.connect", {})
        return await project_on_target(registry, "x", grounder, follow_s=30, max_frames=100)

    outcome = asyncio.run(go())
    assert outcome["ok"] is False and outcome["stage"] == "follow"
    assert outcome["error"]["code"] == "tracking_lost"
    assert not registry.runtime.tracker.active


# ---------- the OpenAI-compatible VLM client ----------

class _FakeVlm(BaseHTTPRequestHandler):
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeVlm.seen.append((self.path, self.headers.get("Authorization"), body))
        if self.headers.get("Authorization") != "Bearer secret":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "nope"}')
            return
        reply = {"choices": [{"message": {"content": '[{"bbox_2d": [10, 20, 30, 40], "label": "ok"}]'}}]}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def vlm_server():
    _FakeVlm.seen = []
    server = HTTPServer(("127.0.0.1", 0), _FakeVlm)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_vlm_client_sends_the_image_and_prompt(vlm_server):
    grounder = openai_compatible_grounder(vlm_server, "secret", "test-model")
    reply = asyncio.run(grounder(b"\xff\xd8jpegbytes", "find the cat"))
    assert "bbox_2d" in reply
    path, auth, body = _FakeVlm.seen[0]
    assert path == "/v1/chat/completions" and auth == "Bearer secret"
    assert body["model"] == "test-model" and body["temperature"] == 0
    image_part, text_part = body["messages"][0]["content"]
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert base64.b64decode(image_part["image_url"]["url"].split(",", 1)[1]) == b"\xff\xd8jpegbytes"
    assert text_part["text"] == "find the cat"


def test_vlm_client_reports_failures(vlm_server):
    wrong_key = openai_compatible_grounder(vlm_server, "wrong", "m")
    with pytest.raises(VlmError, match="HTTP 401"):
        asyncio.run(wrong_key(b"x", "p"))
    unreachable = openai_compatible_grounder("http://127.0.0.1:1/v1", "k", "m", timeout=2)
    with pytest.raises(VlmError):
        asyncio.run(unreachable(b"x", "p"))


# ---------- the examples are runnable as documented ----------

@pytest.mark.parametrize("example, expect", [
    ("basic-projection", "done: the light is off"),
    ("image-projection", "project.image (camera region"),
    ("object-tracking", "tracked 'patch'"),
])
def test_examples_run_in_simulation(example, expect, tmp_path):
    done = subprocess.run(
        [sys.executable, str(ROOT / "examples" / example / "main.py"),
         "--simulate", "--data-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=180, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert expect in done.stdout and done.stdout.rstrip().endswith("done: the light is off")
