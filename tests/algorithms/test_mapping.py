import cv2
import numpy as np
import pytest

from irisgreen_mapping import (
    PROJ_HEIGHT,
    PROJ_WIDTH,
    Calibration,
    camera_point_to_projector,
    homography_is_sane,
    in_projection_field,
    place_in_camera_rect,
    render_camera_polygon,
    solve_homography,
)

H_TRUE = np.array([[1.3, 0.06, 90.0], [-0.05, 1.3, 40.0], [5e-5, 2e-5, 1.0]])


def records(noise=0.0, outlier=None, seed=0):
    rng = np.random.default_rng(seed)
    recs = []
    for x in np.linspace(60, 580, 4):
        for y in np.linspace(60, 420, 3):
            cam = cv2.perspectiveTransform(np.array([[[x, y]]]), H_TRUE).reshape(2)
            cam = cam + rng.normal(0, noise, 2)
            recs.append({"proj": [float(x), float(y)], "cam": [float(cam[0]), float(cam[1])]})
    if outlier is not None:
        recs[outlier]["cam"] = [10.0, 10.0]
    return recs


def test_solve_recovers_homography():
    H, stats = solve_homography(records())
    calib = Calibration(H)
    pts = np.array([[100, 100], [500, 300], [320, 240]], dtype=float)
    expected = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), H_TRUE).reshape(-1, 2)
    assert np.allclose(calib.proj_to_cam(pts), expected, atol=1e-3)
    assert stats["err_max"] < 1e-3


def test_solve_rejects_outlier_and_needs_four_points():
    _, stats = solve_homography(records(noise=0.3, outlier=5))
    assert stats["outliers"] == [5]
    assert stats["err_mean"] < 1.0
    with pytest.raises(ValueError):
        solve_homography(records()[:3])


def test_solve_rejects_a_degenerate_mapping():
    # Every projector point "seen" at nearly the same camera spot: tiny error, garbage fit.
    rng = np.random.default_rng(2)
    recs = records()
    for r in recs:
        r["cam"] = [600.0 + rng.normal(0, 1.0), 400.0 + rng.normal(0, 1.0)]
    with pytest.raises(ValueError):
        solve_homography(recs)


def test_homography_sanity():
    assert homography_is_sane(H_TRUE)
    assert not homography_is_sane(np.zeros((3, 3)))
    assert not homography_is_sane(np.full((3, 3), np.nan))
    flipping = np.array([[1.0, 0, 0], [0, 1.0, 0], [0.01, 0.01, -3.0]])  # divisor changes sign in the field
    assert not homography_is_sane(flipping)


def test_roundtrip_and_persistence(tmp_path):
    calib = Calibration(solve_homography(records())[0])
    pts = np.array([[200.0, 150.0], [400.0, 300.0]])
    assert np.allclose(calib.cam_to_proj(calib.proj_to_cam(pts)), pts, atol=1e-6)

    path = tmp_path / "cal.json"
    calib.save(str(path))
    loaded = Calibration.load(str(path))
    assert np.allclose(loaded.H, calib.H)


def test_load_rejects_bad_files():
    with pytest.raises(ValueError):
        Calibration.from_dict({"schema": "other/1", "H": np.eye(3).tolist()})
    with pytest.raises(ValueError):
        Calibration.from_dict({"schema": "irisgreen.calibration/1", "H": np.zeros((3, 3)).tolist()})


def test_field_checks():
    assert in_projection_field([[0, 0], [639, 479]])
    assert not in_projection_field([[640, 10]])
    assert not in_projection_field([[float("nan"), 1]])
    calib = Calibration(H_TRUE)
    inside = calib.proj_to_cam([320, 240])[0]
    x, y = camera_point_to_projector(calib, inside)
    assert (round(x), round(y)) == (320, 240)
    with pytest.raises(ValueError):
        camera_point_to_projector(calib, (5.0, 5.0))


def test_place_in_camera_rect_keeps_aspect_and_lands_in_rect():
    calib = Calibration(H_TRUE)
    source = np.ones((50, 100), np.uint8)  # 2:1
    rect = (400.0, 250.0, 700.0, 450.0)  # 300x200 camera px
    placed, quad = place_in_camera_rect(source, calib, rect, padding=0.0)
    assert placed.shape == (PROJ_HEIGHT, PROJ_WIDTH) and placed.any()
    cam_quad = calib.proj_to_cam(quad)
    width = np.linalg.norm(cam_quad[1] - cam_quad[0])
    height = np.linalg.norm(cam_quad[3] - cam_quad[0])
    assert abs(width / height - 2.0) < 0.05
    assert (cam_quad[:, 0] >= 399).all() and (cam_quad[:, 0] <= 701).all()

    with pytest.raises(ValueError):
        place_in_camera_rect(source, calib, (0.0, 0.0, 50.0, 50.0))  # off the field
    with pytest.raises(ValueError):
        place_in_camera_rect(source, calib, (10, 10, 5, 5))


def test_render_camera_polygon():
    calib = Calibration(H_TRUE)
    poly = [[400, 250], [700, 250], [700, 450], [400, 450]]
    filled = render_camera_polygon(poly, calib, (1280, 720), mode="shape")
    outline = render_camera_polygon(poly, calib, (1280, 720), mode="stroke", stroke_px=4)
    assert filled.sum() > outline.sum() > 0
    with pytest.raises(ValueError):
        render_camera_polygon([[0, 0], [10, 0], [10, 10]], calib, (1280, 720))
    with pytest.raises(ValueError):
        render_camera_polygon(poly[:2], calib, (1280, 720))
