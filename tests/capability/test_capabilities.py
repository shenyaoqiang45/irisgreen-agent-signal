import asyncio
import base64

import cv2
import numpy as np
import pytest

from irisgreen_capability import CapabilityRegistry
from irisgreen_capability.sim import make_rig, make_sim_runtime
from irisgreen_mapping import Calibration


@pytest.fixture
def stack(tmp_path):
    """Static scene: calibration assumes nothing moves."""
    runtime, rig = make_sim_runtime(make_rig(moving_object=False), data_dir=str(tmp_path))
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


def calibrated(registry):
    results = run_all(registry, [("device.connect", {}), ("calibration.calibrate", {})])
    assert all(r["ok"] for r in results), results
    return results


# ---------- schemas and error envelope ----------

def test_every_capability_has_schemas_and_a_description(stack):
    registry, _, _ = stack
    names = registry.names()
    for expected in [
        "device.connect", "device.disconnect", "device.get_status",
        "project.point", "project.image", "project.clear", "project.status",
        "camera.capture",
        "calibration.load", "calibration.calibrate", "calibration.get_mapping", "calibration.map_point",
        "tracking.start", "tracking.update", "tracking.follow", "tracking.stop",
    ]:
        assert expected in names
    for cap in registry:
        assert cap.description and cap.input_schema["type"] == "object"
        assert cap.output_schema["required"] == ["ok"]
        assert cap.input_schema["additionalProperties"] is False


def test_errors_are_structured_not_raised(stack):
    registry, _, _ = stack
    for name, args, code in [
        ("nope.nothing", {}, "invalid_argument"),
        ("project.point", {"x": "a", "y": 1}, "invalid_argument"),
        ("project.point", {"x": 1, "y": 2, "extra": 1}, "invalid_argument"),
        ("project.point", {"x": 1, "y": 2}, "not_connected"),
        ("calibration.get_mapping", {}, "no_calibration"),
        ("tracking.update", {}, "not_tracking"),
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
    assert status["connected"] and status["camera"] and not status["calibrated"] and not status["tracking"]


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


def test_project_point_in_camera_space_uses_the_calibration(stack):
    registry, runtime, rig = stack
    target_cam = rig.world.H @ np.array([400.0, 300.0, 1.0])
    target_cam = target_cam[:2] / target_cam[2]

    async def go():
        await registry.call("device.connect", {})
        cal = await registry.call("calibration.calibrate", {})
        result = await registry.call(
            "project.point", {"x": float(target_cam[0]), "y": float(target_cam[1]), "space": "camera"}
        )
        far = await registry.call("project.point", {"x": 5.0, "y": 5.0, "space": "camera"})
        return cal, result, far

    cal, result, far = asyncio.run(go())
    assert cal["ok"] and result["ok"]
    assert result["projector"] == pytest.approx([400.0, 300.0], abs=2.0)
    assert rig.world.lit_camera_centroid() == pytest.approx(tuple(target_cam), abs=3.0)
    assert far["error"]["code"] == "out_of_field"


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
    assert [r["error"]["code"] for r in results[2:6]] == ["invalid_argument"] * 4
    assert results[6]["error"]["code"] == "no_calibration"


def test_project_image_in_a_camera_region(stack):
    registry, _, rig = stack
    image = np.full((100, 200), 255, np.uint8)  # 2:1 white slab
    calibrated_steps = [
        ("device.connect", {}),
        ("calibration.calibrate", {}),
        ("project.image", {"image_base64": png_b64(image), "region": [420, 260, 720, 460]}),
    ]
    _, cal, placed = run_all(registry, calibrated_steps)
    assert cal["ok"] and placed["ok"], placed
    cam_quad = Calibration(rig.world.H).proj_to_cam(placed["projector_quad"])
    assert (cam_quad[:, 0] > 400).all() and (cam_quad[:, 0] < 740).all()

    off = run_all(registry, [
        ("project.image", {"image_base64": png_b64(image), "region": [5, 5, 60, 60]}),
    ])[0]
    assert off["error"]["code"] == "out_of_field"


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


# ---------- camera and calibration ----------

def test_camera_capture_returns_a_decodable_jpeg_with_optional_overlay(stack):
    registry, _, _ = stack
    plain = call(registry, "camera.capture", quality=60)
    assert plain["ok"] and (plain["width"], plain["height"]) == (1280, 720)
    frame = cv2.imdecode(np.frombuffer(base64.b64decode(plain["image_base64"]), np.uint8), cv2.IMREAD_COLOR)
    assert frame.shape[:2] == (720, 1280)

    assert call(registry, "camera.capture", overlay_field=True)["error"]["code"] == "no_calibration"
    calibrated(registry)
    overlay = call(registry, "camera.capture", overlay_field=True)
    assert overlay["ok"]


def test_calibrate_save_load_and_map_point(stack, tmp_path):
    registry, runtime, rig = stack
    run_all(registry, [("device.connect", {})])
    cal = asyncio.run(registry.call("calibration.calibrate", {"save_path": "cal.json"}))
    assert cal["ok"] and cal["stats"]["err_mean"] < 1.0
    assert (tmp_path / "cal.json").exists()

    runtime.calibration = None
    loaded = call(registry, "calibration.load", path="cal.json")
    assert loaded["ok"] and np.allclose(loaded["H"], cal["H"])

    mapped = call(registry, "calibration.map_point", x=400, y=300, source="projector")
    truth = rig.world.H @ np.array([400.0, 300.0, 1.0])
    assert (mapped["x"], mapped["y"]) == pytest.approx(tuple(truth[:2] / truth[2]), abs=2.0)
    back = call(registry, "calibration.map_point", x=mapped["x"], y=mapped["y"], source="camera")
    assert (back["x"], back["y"]) == pytest.approx((400.0, 300.0), abs=1e-3) and back["in_field"]

    assert call(registry, "calibration.load", path="missing.json")["error"]["code"] == "invalid_argument"
    assert call(registry, "calibration.load", path="../cal.json")["error"]["code"] == "invalid_argument"


def test_calibration_failure_is_reported_and_the_light_is_cleared(stack):
    registry, runtime, rig = stack
    rig.world.render = lambda: rig.world._wall.copy()  # the camera never sees the projection
    results = run_all(registry, [("device.connect", {}), ("calibration.calibrate", {})])
    assert results[1]["error"]["code"] == "calibration_failed"
    assert runtime.calibration is None and not rig.world.mask.any()


def test_calibrating_while_the_scene_moves_fails_instead_of_returning_garbage(tmp_path):
    runtime, rig = make_sim_runtime(make_rig(moving_object=True), data_dir=str(tmp_path))
    rig.world.still_when = None  # force the object to keep moving during calibration
    registry = CapabilityRegistry(runtime)
    results = run_all(registry, [("device.connect", {}), ("calibration.calibrate", {})])
    assert results[1]["ok"] is False
    assert results[1]["error"]["code"] == "calibration_failed"
    assert runtime.calibration is None


def test_calibrate_needs_a_connected_device(stack):
    registry, _, _ = stack
    assert call(registry, "calibration.calibrate")["error"]["code"] == "not_connected"
