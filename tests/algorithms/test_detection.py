import json

import cv2
import numpy as np
import pytest

from irisgreen_detection import detect_dot, regions_from_reply, to_1bpp
from irisgreen_detection.grounding import extract_json_value, refine_outline


def frame_with_dot(cx, cy, radius=10, size=(480, 640)):
    frame = np.full((*size, 3), 70, np.uint8)
    cv2.circle(frame, (cx, cy), radius, (60, 255, 60), -1)
    return frame


def test_detect_dot_subpixel_centroid_against_background():
    bg = np.full((480, 640, 3), 70, np.uint8)
    (cx, cy), area = detect_dot(frame_with_dot(300, 200), bg)
    assert abs(cx - 300) < 1.0 and abs(cy - 200) < 1.0
    assert area > 200


def test_detect_dot_rejects_edges_strips_and_empty_frames():
    bg = np.full((480, 640, 3), 70, np.uint8)
    assert detect_dot(bg, bg)[0] is None

    strip = bg.copy()
    strip[200:204, 100:500] = (60, 255, 60)  # long thin reflection
    assert detect_dot(strip, bg)[0] is None

    edge = frame_with_dot(8, 8, radius=6)  # inside the ignored border
    assert detect_dot(edge, bg)[0] is None


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


def test_regions_from_reply_handles_prose_and_clamps():
    reply = (
        "Here you go:\n```json\n"
        + json.dumps([{"label": "cat", "bbox_2d": [100, 200, 500, 900],
                       "outline": [[100, 200], [500, 200], [300, 900]]}])
        + "\n```"
    )
    (region,) = regions_from_reply(reply, 1000, 500)
    assert region["label"] == "cat"
    assert region["bbox"] == (100.0, 100.0, 500.0, 450.0)
    assert len(region["polygon"]) == 3

    clamped = regions_from_reply('[{"bbox_2d": [-50, 0, 2000, 1000]}]', 640, 480)[0]["bbox"]
    assert clamped == (0.0, 0.0, 639.0, 479.0)


def test_regions_from_reply_rejects_garbage():
    with pytest.raises(ValueError):
        regions_from_reply("no json here", 100, 100)
    with pytest.raises(ValueError):
        regions_from_reply('[{"bbox_2d": [500, 500, 100, 100]}]', 100, 100)
    assert extract_json_value('noise {"a": 1} tail') == {"a": 1}


def test_refine_outline_finds_a_bright_object():
    frame = np.full((240, 320, 3), 30, np.uint8)
    cv2.rectangle(frame, (100, 80), (220, 170), (230, 230, 230), -1)
    polygon = refine_outline(frame, (95, 75, 225, 175))
    xs, ys = zip(*polygon)
    assert 95 <= min(xs) <= 110 and 210 <= max(xs) <= 225
    assert 75 <= min(ys) <= 90 and 160 <= max(ys) <= 175
    with pytest.raises(ValueError):
        refine_outline(frame, (10, 10, 20, 20))
