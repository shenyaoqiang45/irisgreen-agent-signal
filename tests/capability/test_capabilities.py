import asyncio
import base64

import cv2
import numpy as np
import pytest

from irisgreen_capability import CapabilityRegistry
from irisgreen_capability.render import make_dot_image, to_1bpp
from irisgreen_capability.sim import make_sim_runtime


@pytest.fixture
def stack(tmp_path):
    runtime, rig = make_sim_runtime(data_dir=str(tmp_path))
    return CapabilityRegistry(runtime), runtime, rig


def call(registry, name, **args):
    return asyncio.run(registry.call(name, args))


def run_all(registry, steps):
    """Run several calls inside ONE event loop (the device lock is loop-bound)."""
    async def go():
        return [await registry.call(name, args) for name, args in steps]
    return asyncio.run(go())


def png_b64(image: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", image)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


# ---------- schemas and error envelope ----------

def test_every_capability_has_schemas_and_a_description(stack):
    registry, _, _ = stack
    assert registry.names() == [
        "device.connect", "device.disconnect", "device.get_status",
        "project.point", "project.image", "project.animation", "project.clear", "project.status",
    ]
    for cap in registry:
        assert cap.description and cap.input_schema["type"] == "object"
        assert cap.output_schema["required"] == ["ok"]
        assert cap.input_schema["additionalProperties"] is False


def test_errors_are_structured_not_raised(stack):
    registry, _, _ = stack
    for name, args, code in [
        ("nope.nothing", {}, "invalid_argument"),
        ("camera.capture", {}, "invalid_argument"),
        ("project.point", {"x": "a", "y": 1}, "invalid_argument"),
        ("project.point", {"x": 1, "y": 2, "extra": 1}, "invalid_argument"),
        ("project.point", {"x": 1, "y": 2, "space": "camera"}, "invalid_argument"),
        ("project.point", {"x": 1, "y": 2}, "not_connected"),
    ]:
        result = call(registry, name, **args)
        assert result["ok"] is False and result["error"]["code"] == code, (name, result)


# ---------- device and projection ----------

def test_connect_reports_identity_and_is_idempotent(stack):
    registry, _, _ = stack
    first, second, status = run_all(registry, [
        ("device.connect", {}), ("device.connect", {}), ("device.get_status", {}),
    ])
    assert first["ok"] and first["model"] == "IrisGreen" and first["serial"] == "SIM0001"
    assert second["already_connected"] is True
    assert status["connected"] and not status["projecting"]


def test_project_point_lights_the_expected_pixel(stack):
    registry, _, rig = stack
    connected, point, status = run_all(registry, [
        ("device.connect", {}),
        ("project.point", {"x": 320, "y": 240, "radius": 10}),
        ("project.status", {}),
    ])
    assert point["ok"] and point["projector"] == [320, 240]
    assert status["projecting"] is True
    ys, xs = np.nonzero(rig.world.mask)
    assert abs(xs.mean() - 320) < 1 and abs(ys.mean() - 240) < 1
    assert rig.world.playing


def test_project_point_rejects_outside_the_field(stack):
    registry, _, _ = stack
    run_all(registry, [("device.connect", {})])
    for x, y in [(640, 10), (-1, 5), (10, 480), (700, 10)]:
        result = call(registry, "project.point", x=x, y=y)
        assert result["error"]["code"] == "out_of_field", (x, y, result)


def test_project_image_fills_the_field_and_validates_input(stack):
    registry, _, rig = stack
    image = np.zeros((120, 160), np.uint8)
    cv2.circle(image, (80, 60), 40, 255, -1)
    results = run_all(registry, [
        ("device.connect", {}),
        ("project.image", {"image_base64": png_b64(image)}),
        ("project.image", {}),
        ("project.image", {"image_base64": png_b64(image), "image_path": "x.png"}),
        ("project.image", {"image_base64": "not base64!!"}),
        ("project.image", {"image_base64": base64.b64encode(b"not an image").decode()}),
        ("project.image", {"image_base64": png_b64(image), "region": [300, 200, 600, 400]}),
    ])
    assert results[1]["ok"] and results[1]["lit_pixels"] > 10000
    assert rig.world.mask.shape == (480, 640)
    assert [r["error"]["code"] for r in results[2:7]] == ["invalid_argument"] * 5


def test_project_image_is_pre_mirrored_when_enabled(stack, tmp_path):
    registry, runtime, rig = stack
    runtime.mirror_full_field = True
    image = np.zeros((480, 640), np.uint8)
    image[:, :100] = 255  # a bar on the left edge
    cv2.imwrite(str(tmp_path / "bar.png"), image)
    run_all(registry, [("device.connect", {}), ("project.image", {"image_path": "bar.png"})])
    assert rig.world.mask[:, -100:].all() and not rig.world.mask[:, :100].any()


def test_project_animation_stores_frames_in_group_one_and_replaces_stale_ones(stack):
    registry, _, rig = stack
    frames = [np.full((120, 160), v, np.uint8) for v in (255, 0, 255)]
    items = [{"image_base64": png_b64(f)} for f in frames]
    results = run_all(registry, [
        ("device.connect", {}),
        ("project.animation", {"frames": items, "frame_ms": 250, "seconds": 12}),
        ("project.status", {}),
        ("project.animation", {"frames": items[:2]}),
        ("project.image", {"image_base64": items[0]["image_base64"]}),
    ])
    first, status = results[1], results[2]
    assert first["ok"] and first["frames"] == 3 and first["lit_pixels"][1] == 0 and first["lit_pixels"][0] > 0
    assert status["last_projection"]["frames"] == 3 and status["last_projection"]["frame_ms"] == 300  # 250 ms rounds to the device's 100 ms unit
    assert results[3]["ok"] and results[4]["ok"]
    names = [n for n, _ in rig.world.uploads]
    assert names == ["1_1.bmp", "1_2.bmp", "1_3.bmp", "1_1.bmp", "1_2.bmp", "1_1.bmp"]
    # the single image started from a cleared group: no frame 2 left to play
    assert list(rig.world.files) == ["1_1.bmp"]
    play = [c for c in rig.transport.commands if c[0] == 0xA0]
    assert play[0][2:] == bytes([1, 120, 0, 3, 0, 1])  # loop, 12 s, 250 ms -> 3 units, group 1


def test_project_animation_default_frame_time_is_150ms_rounded_to_the_device_step(stack):
    registry, _, rig = stack
    items = [{"image_base64": png_b64(np.full((20, 20), 255, np.uint8))}] * 2
    run_all(registry, [("device.connect", {}), ("project.animation", {"frames": items, "seconds": 10})])
    play = [c for c in rig.transport.commands if c[0] == 0xA0]
    assert play[0][2:] == bytes([1, 100, 0, 2, 0, 1])  # 150 ms -> 2 units of 100 ms


def test_project_animation_validates_frames(stack):
    registry, _, rig = stack
    image = png_b64(np.full((20, 20), 255, np.uint8))
    run_all(registry, [("device.connect", {})])
    too_many = [{"image_base64": image}] * 11
    for frames in ([], too_many, [{}], [{"image_base64": image, "image_path": "a.png"}]):
        result = call(registry, "project.animation", frames=frames)
        assert result["ok"] is False and result["error"]["code"] == "invalid_argument", frames
    assert rig.world.uploads == []


def test_project_image_path_cannot_escape_the_data_directory(stack, tmp_path):
    registry, runtime, _ = stack
    outside = tmp_path.parent / "secret.png"
    cv2.imwrite(str(outside), np.full((10, 10), 255, np.uint8))
    cv2.imwrite(str(tmp_path / "ok.png"), np.full((10, 10), 255, np.uint8))
    results = run_all(registry, [
        ("device.connect", {}),
        ("project.image", {"image_path": "../secret.png"}),
        ("project.image", {"image_path": str(outside)}),
        ("project.image", {"image_path": "ok.png"}),
    ])
    assert results[1]["error"]["code"] == "invalid_argument"
    assert results[2]["error"]["code"] == "invalid_argument"
    assert results[3]["ok"]


def test_clear_turns_the_light_off(stack):
    registry, _, rig = stack
    results = run_all(registry, [
        ("device.connect", {}),
        ("project.point", {"x": 100, "y": 100}),
        ("project.clear", {}),
        ("project.status", {}),
    ])
    assert results[2]["ok"] and results[3]["projecting"] is False
    assert not rig.world.mask.any()


def test_disconnect_then_project_fails(stack):
    registry, _, _ = stack
    results = run_all(registry, [
        ("device.connect", {}), ("device.disconnect", {}), ("project.point", {"x": 1, "y": 1}),
    ])
    assert results[1]["ok"] and results[2]["error"]["code"] == "not_connected"


def test_connect_uses_the_default_address_when_none_is_given(tmp_path):
    runtime, _ = make_sim_runtime(data_dir=str(tmp_path))
    seen = []
    inner = runtime.transport_factory

    async def spy(address):
        seen.append(address)
        return await inner(address)

    runtime.transport_factory = spy
    runtime.default_address = "AA:BB"
    registry = CapabilityRegistry(runtime)
    results = run_all(registry, [
        ("device.connect", {}), ("device.disconnect", {}), ("device.connect", {"address": "CC:DD"}),
    ])
    assert all(r["ok"] for r in results) and seen == ["AA:BB", "CC:DD"]


def test_a_dropped_link_is_reconnected_before_the_next_projection(stack):
    registry, runtime, rig = stack
    run_all(registry, [("device.connect", {})])
    rig.transport.connected = False  # the device or the OS closed the link while idle

    async def go():
        return [await registry.call("project.point", {"x": 100, "y": 100}), await registry.call("project.clear", {})]

    shown, cleared = asyncio.run(go())
    assert shown["ok"] and cleared["ok"] and rig.transport.connected
    assert not rig.world.mask.any()


# ---------- rendering ----------

def test_dot_image_has_one_filled_dot():
    dot = make_dot_image(100, 50, 5)
    ys, xs = np.nonzero(dot)
    assert dot.shape == (480, 640) and abs(xs.mean() - 100) < 0.5 and abs(ys.mean() - 50) < 0.5


def test_to_1bpp_modes():
    gray = np.tile(np.arange(256, dtype=np.uint8), (64, 1))
    assert set(np.unique(to_1bpp(gray, "threshold"))) == {0, 1}
    assert np.array_equal(to_1bpp(gray, "threshold_inv"), 1 - to_1bpp(gray, "threshold"))
    otsu = to_1bpp(gray, "otsu")
    assert 0.3 < otsu.mean() < 0.7

    small = np.full((24, 24), 128, np.uint8)
    # A flat mid-grey halftones to roughly its brightness, unlike a hard threshold.
    assert 0.2 < to_1bpp(small, "dither_flat").mean() < 0.8
    assert to_1bpp(np.zeros((40, 40), np.uint8), "edges").sum() == 0
    with pytest.raises(ValueError):
        to_1bpp(gray, "nope")
