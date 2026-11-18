"""Hikrobot (Hikvision) industrial camera through the MVS SDK, as a :class:`Camera`.

USB3 Vision cameras are not UVC, so OpenCV cannot open them; they need the MVS
SDK. Its ctypes binding ships with MVS and is not a pip package, so its
directory is added to ``sys.path`` at first use. Resolution order for the MVS
install: constructor ``mvs_dir`` > ``$MVS_DIR`` > the default install path.

Frames are returned as BGR uint8. A monochrome camera yields a grey image, so
anything that detects the laser spot must use brightness gain, not colour.
"""

from __future__ import annotations

import asyncio
import os
import sys
from ctypes import POINTER, byref, c_ubyte, cast, memset, sizeof

import numpy as np

from .camera import Camera
from .errors import NO_CAMERA, CapabilityError

DEFAULT_MVS_DIR = r"C:\Program Files (x86)\MVS"
_MVIMPORT = os.path.join("Development", "Samples", "Python", "MvImport")
_RUNTIME_DIRS = (
    r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64",
    r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win32_i86",
)
_MONO8 = 0x01080001
_BGR8 = 0x02180014


def _decode(raw) -> str:
    return bytes(raw).split(b"\x00")[0].decode("utf-8", "replace")


def _load_binding(mvs_dir: str | None):
    base = mvs_dir or os.environ.get("MVS_DIR") or DEFAULT_MVS_DIR
    path = os.path.join(base, _MVIMPORT)
    if not os.path.isfile(os.path.join(path, "MvCameraControl_class.py")):
        raise CapabilityError(
            NO_CAMERA,
            f"MVS Python binding not found at {path}; install the MVS client "
            "or set MVS_DIR to its install directory",
        )
    # The binding loads MvCameraControl.dll by bare name, so its runtime dir must be searchable.
    for runtime in _RUNTIME_DIRS if sys.maxsize > 2**32 else reversed(_RUNTIME_DIRS):
        if os.path.isfile(os.path.join(runtime, "MvCameraControl.dll")):
            os.environ["PATH"] = runtime + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(runtime)
            except (AttributeError, OSError):
                pass
            break
    if path not in sys.path:
        sys.path.insert(0, path)
    import MvCameraControl_class  # type: ignore

    return MvCameraControl_class


class HikCamera(Camera):
    """One Hikrobot camera. Opened lazily, on a worker thread, at the first grab.

    serial: pick this camera; default is the first USB3 camera (the device list
        order is not stable and may start with GigE devices that cannot be opened).
    exposure_us / gain_db: set manually when given; otherwise the camera keeps
        its current values. For a laser dot, a short fixed exposure keeps the
        dot from saturating the sensor.
    flush: frames discarded before each returned frame, because the SDK buffers
        frames captured with older settings.
    """

    def __init__(
        self,
        serial: str | None = None,
        *,
        exposure_us: float | None = None,
        gain_db: float | None = None,
        flush: int = 2,
        mvs_dir: str | None = None,
    ):
        self.serial = serial
        self.exposure_us = exposure_us
        self.gain_db = gain_db
        self._flush = flush
        self._mvs_dir = mvs_dir
        self._mv = None
        self._cam = None
        self.model = ""
        self.size = (0, 0)
        self._lock = asyncio.Lock()

    # ---------- blocking SDK calls (run on a worker thread) ----------

    def _enumerate(self) -> list[tuple[int, str, str, str, object]]:
        mv = self._mv
        dev_list = mv.MV_CC_DEVICE_INFO_LIST()
        ret = mv.MvCamera.MV_CC_EnumDevices(mv.MV_GIGE_DEVICE | mv.MV_USB_DEVICE, dev_list)
        if ret != 0:
            raise CapabilityError(NO_CAMERA, f"camera enumeration failed: 0x{ret:08x}")
        found = []
        for i in range(dev_list.nDeviceNum):
            info = cast(dev_list.pDeviceInfo[i], POINTER(mv.MV_CC_DEVICE_INFO)).contents
            if info.nTLayerType == mv.MV_USB_DEVICE:
                d = info.SpecialInfo.stUsb3VInfo
                found.append((i, "USB3", _decode(d.chModelName), _decode(d.chSerialNumber), info))
            elif info.nTLayerType == mv.MV_GIGE_DEVICE:
                d = info.SpecialInfo.stGigEInfo
                found.append((i, "GigE", _decode(d.chModelName), _decode(d.chSerialNumber), info))
        return found

    def _open(self) -> None:
        self._mv = _load_binding(self._mvs_dir)
        mv = self._mv
        found = self._enumerate()
        if self.serial is not None:
            matches = [c for c in found if c[3] == self.serial]
        else:
            matches = [c for c in found if c[1] == "USB3"]
        if not matches:
            listing = [(c[1], c[2], c[3]) for c in found]
            raise CapabilityError(
                NO_CAMERA,
                f"no Hik camera {self.serial or '(USB3)'} found; enumerated: {listing}",
            )
        _, _, self.model, self.serial, info = matches[0]

        cam = mv.MvCamera()
        ret = cam.MV_CC_CreateHandle(info)
        if ret != 0:
            raise CapabilityError(NO_CAMERA, f"cannot create camera handle: 0x{ret:08x}")
        ret = cam.MV_CC_OpenDevice(mv.MV_ACCESS_Exclusive, 0)
        if ret != 0:
            cam.MV_CC_DestroyHandle()
            raise CapabilityError(
                NO_CAMERA, f"cannot open camera {self.serial}: 0x{ret:08x} (in use by another program?)"
            )
        cam.MV_CC_SetEnumValue("TriggerMode", 0)  # free-run
        if self.exposure_us is not None:
            cam.MV_CC_SetEnumValue("ExposureAuto", 0)
            cam.MV_CC_SetFloatValue("ExposureTime", float(self.exposure_us))
        if self.gain_db is not None:
            cam.MV_CC_SetEnumValue("GainAuto", 0)
            cam.MV_CC_SetFloatValue("Gain", float(self.gain_db))
        ret = cam.MV_CC_StartGrabbing()
        if ret != 0:
            cam.MV_CC_CloseDevice()
            cam.MV_CC_DestroyHandle()
            raise CapabilityError(NO_CAMERA, f"cannot start grabbing: 0x{ret:08x}")
        self._cam = cam
        self.size = (self._get_int("Width"), self._get_int("Height"))

    def _get_int(self, key: str) -> int:
        value = self._mv.MVCC_INTVALUE()
        memset(byref(value), 0, sizeof(value))
        return int(value.nCurValue) if self._cam.MV_CC_GetIntValue(key, value) == 0 else 0

    def _one_frame(self, timeout_ms: int) -> np.ndarray | None:
        mv = self._mv
        w, h = self.size
        size = w * h * 4 + 2048
        buf = (c_ubyte * size)()
        frame_info = mv.MV_FRAME_OUT_INFO_EX()
        memset(byref(frame_info), 0, sizeof(frame_info))
        if self._cam.MV_CC_GetOneFrameTimeout(byref(buf), size, frame_info, timeout_ms) != 0:
            return None
        return self._to_bgr(np.frombuffer(buf, dtype=np.uint8, count=frame_info.nFrameLen), frame_info)

    def _to_bgr(self, src: np.ndarray, info) -> np.ndarray:
        w, h, ptype = info.nWidth, info.nHeight, info.enPixelType
        if ptype == _MONO8:
            gray = src[: w * h].reshape(h, w)
            return np.stack([gray, gray, gray], axis=-1)
        if ptype == _BGR8:
            return src[: w * h * 3].reshape(h, w, 3).copy()
        # Bayer, YUV, ...: let the SDK convert.
        mv = self._mv
        dst = (c_ubyte * (w * h * 3))()
        param = mv.MV_CC_PIXEL_CONVERT_PARAM()
        memset(byref(param), 0, sizeof(param))
        param.nWidth, param.nHeight = w, h
        param.enSrcPixelType = ptype
        param.pSrcData = src.ctypes.data_as(POINTER(c_ubyte))
        param.nSrcDataLen = len(src)
        param.enDstPixelType = _BGR8
        param.pDstBuffer = cast(dst, POINTER(c_ubyte))
        param.nDstBufferSize = w * h * 3
        ret = self._cam.MV_CC_ConvertPixelType(param)
        if ret != 0:
            raise CapabilityError(NO_CAMERA, f"pixel conversion failed (type 0x{ptype:08x}): 0x{ret:08x}")
        return np.frombuffer(dst, dtype=np.uint8).reshape(h, w, 3).copy()

    def _read(self) -> np.ndarray:
        frame = None
        for _ in range(self._flush + 1):
            grabbed = self._one_frame(1000)
            if grabbed is not None:
                frame = grabbed
        if frame is None:
            raise CapabilityError(NO_CAMERA, "the Hik camera returned no frame")
        return frame

    def _close(self) -> None:
        if self._cam is not None:
            self._cam.MV_CC_StopGrabbing()
            self._cam.MV_CC_CloseDevice()
            self._cam.MV_CC_DestroyHandle()
            self._cam = None

    # ---------- Camera ----------

    async def grab(self) -> np.ndarray:
        async with self._lock:
            if self._cam is None:
                await asyncio.to_thread(self._open)
        return await asyncio.to_thread(self._read)

    async def close(self) -> None:
        await asyncio.to_thread(self._close)

    def describe(self) -> str:
        return f"{self.model} sn={self.serial} {self.size[0]}x{self.size[1]}"
