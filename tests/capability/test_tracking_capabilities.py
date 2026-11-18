import asyncio

import numpy as np
import pytest

from irisgreen_capability import CapabilityRegistry
from irisgreen_capability.sim import make_rig, make_sim_runtime


@pytest.fixture
def moving(tmp_path):
    runtime, rig = make_sim_runtime(make_rig(moving_object=True), data_dir=str(tmp_path))
    return CapabilityRegistry(runtime), runtime, rig


def obj_bbox(rig):
    o = rig.world.objects[0]
    return [o.x, o.y, o.width, o.height]


async def ready(registry, rig):
    """Connect and calibrate on a still scene, then let the object move."""
    rig.world.paused = True
    assert (await registry.call("device.connect", {}))["ok"]
    assert (await registry.call("calibration.calibrate", {}))["ok"]
    rig.world.paused = False


def test_update_keeps_the_dot_on_the_moving_object(moving):
    registry, _, rig = moving
    errors = []

    async def go():
        await ready(registry, rig)
        started = await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        assert started["ok"], started
        for _ in range(25):
            r = await registry.call("tracking.update", {})
            assert r["ok"], r
            assert r["aimed"]["projected"], r
            lit = rig.world.lit_camera_centroid()
            true = rig.world.objects[0].center
            errors.append(float(np.hypot(lit[0] - true[0], lit[1] - true[1])))

    asyncio.run(go())
    # The reference template tracker is pulled a few pixels by the projected dot's own
    # appearance on the object (a 90x70 px target here); stronger Measurers do better.
    assert max(errors) < 12.0, errors
    assert np.mean(errors) < 8.0


def test_follow_reports_a_summary(moving):
    registry, runtime, rig = moving

    async def go():
        await ready(registry, rig)
        await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        return await registry.call("tracking.follow", {"duration_s": 3, "max_frames": 100})

    result = asyncio.run(go())
    assert result["ok"], result
    assert 25 <= result["frames"] <= 32  # 3 s at 0.1 s per frame
    assert result["aimed_frames"] >= result["frames"] - 2
    assert result["last"]["measured"]


def test_follow_respects_max_frames(moving):
    registry, _, rig = moving

    async def go():
        await ready(registry, rig)
        await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        return await registry.call("tracking.follow", {"duration_s": 60, "max_frames": 4})

    assert asyncio.run(go())["frames"] == 4


def test_update_without_aim_does_not_project(moving):
    registry, _, rig = moving

    async def go():
        await ready(registry, rig)
        before = len(rig.world.uploads)
        await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        result = await registry.call("tracking.update", {"aim": False})
        return before, result

    before, result = asyncio.run(go())
    assert result["ok"] and result["aimed"] is None
    assert len(rig.world.uploads) == before


def test_object_disappearing_is_reported_as_lost_and_resets(moving):
    registry, runtime, rig = moving

    async def go():
        await ready(registry, rig)
        await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        rig.world.objects.clear()
        outcomes = []
        for _ in range(15):
            r = await registry.call("tracking.update", {"aim": False})
            outcomes.append(r)
            if not r["ok"]:
                break
        again = await registry.call("tracking.update", {})
        return outcomes, again

    outcomes, again = asyncio.run(go())
    assert outcomes[-1]["error"]["code"] == "tracking_lost"
    assert not outcomes[-1]["ok"] and len(outcomes) > 1  # it coasted before giving up
    assert not runtime.tracker.active
    assert again["error"]["code"] == "not_tracking"


def test_follow_returns_the_loss_with_progress(moving):
    registry, _, rig = moving

    async def go():
        await ready(registry, rig)
        await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        rig.world.objects.clear()
        return await registry.call("tracking.follow", {"duration_s": 30, "max_frames": 100})

    result = asyncio.run(go())
    assert result["error"]["code"] == "tracking_lost" and result["frames"] >= 1


def test_target_outside_the_field_is_reported_not_projected(moving):
    registry, _, rig = moving

    async def go():
        await ready(registry, rig)
        o = rig.world.objects[0]
        o.x, o.y, o.vx, o.vy = 1100.0, 600.0, 0.0, 0.0  # beyond the projectable area
        o.bounds = (0.0, 0.0, 1280.0, 720.0)
        await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        return await registry.call("tracking.update", {})

    result = asyncio.run(go())
    assert result["ok"] and result["aimed"] == {"projected": False, "reason": "out_of_field"}


def test_start_validates_and_stop_resets(moving):
    registry, runtime, rig = moving

    async def go():
        await ready(registry, rig)
        bad = await registry.call("tracking.start", {"bbox": [10, 10, 2, 2]})
        short = await registry.call("tracking.start", {"bbox": [1, 2, 3]})
        ok = await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        stopped = await registry.call("tracking.stop", {})
        after = await registry.call("tracking.update", {})
        return bad, short, ok, stopped, after

    bad, short, ok, stopped, after = asyncio.run(go())
    assert bad["error"]["code"] == "invalid_argument"
    assert short["error"]["code"] == "invalid_argument"
    assert ok["ok"] and stopped["ok"] and after["error"]["code"] == "not_tracking"
    assert not runtime.tracker.active


def test_tracking_needs_a_camera_and_a_calibration_to_aim(tmp_path):
    runtime, rig = make_sim_runtime(make_rig(moving_object=True), data_dir=str(tmp_path))
    registry = CapabilityRegistry(runtime)

    async def go():
        await registry.call("device.connect", {})
        await registry.call("tracking.start", {"bbox": obj_bbox(rig)})
        return await registry.call("tracking.update", {})

    result = asyncio.run(go())  # tracking works, but aiming without calibration cannot
    assert result["ok"] is False and result["error"]["code"] == "no_calibration"
