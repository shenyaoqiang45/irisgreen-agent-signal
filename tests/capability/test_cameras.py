import asyncio

import pytest

from irisgreen_capability import HikCamera, OpenCvCamera
from irisgreen_capability.errors import CapabilityError


def test_constructing_a_camera_never_touches_the_hardware(monkeypatch):
    import cv2

    def boom(*args, **kwargs):
        raise AssertionError("camera opened at construction")

    monkeypatch.setattr(cv2, "VideoCapture", boom)
    OpenCvCamera(0)
    # Opening on the main thread breaks Bleak on Windows (COM apartment), so it must wait for grab().
    HikCamera("K0000000", exposure_us=5000)


def test_hik_reports_a_missing_mvs_sdk_as_no_camera(tmp_path, monkeypatch):
    monkeypatch.delenv("MVS_DIR", raising=False)
    camera = HikCamera(mvs_dir=str(tmp_path / "no-mvs-here"))
    with pytest.raises(CapabilityError) as info:
        asyncio.run(camera.grab())
    assert info.value.code == "no_camera" and "MVS" in info.value.message


def test_opencv_reports_an_unopenable_camera_as_no_camera(monkeypatch):
    import cv2

    class Closed:
        def isOpened(self):
            return False

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: Closed())
    with pytest.raises(CapabilityError) as info:
        asyncio.run(OpenCvCamera(7).grab())
    assert info.value.code == "no_camera" and "7" in info.value.message
