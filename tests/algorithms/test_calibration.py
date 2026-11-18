import asyncio

import numpy as np
import pytest

from irisgreen_calibration import CalibrationError, calibrate, grid_points, verify
from irisgreen_capability.sim import SimCamera, SimWorld
from irisgreen_mapping import PROJ_HEIGHT, PROJ_WIDTH


def rig():
    world = SimWorld()
    camera = SimCamera(world, dt_per_grab=0.0)

    async def show(mask):
        world.mask = mask
        world.playing = True

    return world, camera, show


def test_grid_points_are_inset_and_row_major():
    pts = grid_points(4, 3, margin=0.1)
    assert len(pts) == 12
    assert pts[0] == (PROJ_WIDTH * 0.1, PROJ_HEIGHT * 0.1)
    assert pts[3][1] == pts[0][1] and pts[4][1] > pts[0][1]


def test_calibrate_recovers_the_true_mapping():
    world, camera, show = rig()
    result = asyncio.run(calibrate(show, camera.grab, settle_s=0))
    assert result.stats["detected"] == 12
    assert result.stats["err_mean"] < 1.0

    for proj in [(100, 100), (320, 240), (550, 400)]:
        predicted = result.calibration.proj_to_cam(proj)[0]
        truth = world.H @ np.array([*proj, 1.0])
        truth = truth[:2] / truth[2]
        assert np.linalg.norm(predicted - truth) < 2.0


def test_verify_reports_small_errors():
    world, camera, show = rig()
    result = asyncio.run(calibrate(show, camera.grab, settle_s=0))
    report = asyncio.run(verify(result.calibration, show, camera.grab, settle_s=0))
    assert report["detected"] == report["points"] == 5
    assert report["max_px"] < 3.0


def test_calibrate_fails_when_nothing_is_visible():
    world, camera, _ = rig()

    async def show_nothing(mask):  # projection never reaches the camera
        world.playing = False

    with pytest.raises(CalibrationError, match="found only 0"):
        asyncio.run(calibrate(show_nothing, camera.grab, settle_s=0))


def test_calibrate_rejects_a_fit_that_only_explains_a_few_dots():
    world, camera, show = rig()
    calls = {"n": 0}

    async def scrambled_grab():
        calls["n"] += 1
        frame = await camera.grab()
        if calls["n"] in {3, 5, 7, 9, 11}:  # 5 of the 12 dots land somewhere else
            frame = np.roll(frame, (97 * calls["n"], 53 * calls["n"]), axis=(1, 0))
        return frame

    with pytest.raises(CalibrationError, match="agree on one mapping"):
        asyncio.run(calibrate(show, scrambled_grab, settle_s=0))


def test_calibrate_rejects_an_implausible_fit():
    world, camera, show = rig()
    calls = {"n": 0}

    async def scrambled_grab():
        calls["n"] += 1
        frame = await camera.grab()
        if calls["n"] > 1:  # every dot somewhere else
            frame = np.roll(frame, (97 * calls["n"], 53 * calls["n"]), axis=(1, 0))
        return frame

    with pytest.raises(CalibrationError):
        asyncio.run(calibrate(show, scrambled_grab, settle_s=0))


def test_calibrate_tolerates_one_bad_dot():
    world, camera, show = rig()
    calls = {"n": 0}

    async def one_bad_grab():
        calls["n"] += 1
        frame = await camera.grab()
        if calls["n"] == 6:
            frame = np.roll(frame, (211, 97), axis=(1, 0))
        return frame

    result = asyncio.run(calibrate(show, one_bad_grab, settle_s=0))
    assert result.stats["inliers"] == 11 and result.stats["err_mean"] < 1.0


def test_calibrate_validates_grid():
    _, camera, show = rig()
    with pytest.raises(ValueError):
        asyncio.run(calibrate(show, camera.grab, cols=1, rows=3, settle_s=0))
