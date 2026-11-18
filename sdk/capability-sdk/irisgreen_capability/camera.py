"""Camera abstraction. The capability layer only needs BGR frames."""

from __future__ import annotations

import asyncio
import sys
from abc import ABC, abstractmethod

import numpy as np

from .errors import NO_CAMERA, CapabilityError


class Camera(ABC):
    @abstractmethod
    async def grab(self) -> np.ndarray:
        """Return the newest BGR uint8 frame."""

    async def close(self) -> None:
        """Release the camera. Default: nothing to release."""


class StaticCamera(Camera):
    """Always returns the same frame (tests, recorded scenes)."""

    def __init__(self, frame: np.ndarray):
        self._frame = frame

    async def grab(self) -> np.ndarray:
        return self._frame.copy()


class OpenCvCamera(Camera):
    """A USB / built-in camera through OpenCV.

    The device is opened lazily, on a worker thread, at the first grab. On
    Windows, DirectShow initialises COM as a single-threaded apartment on the
    thread that opens the camera; doing that on the thread that runs the event
    loop makes Bleak fail with "Thread is configured for Windows GUI".
    """

    def __init__(self, index: int = 0, width: int = 1280, height: int = 720, flush: int = 4):
        self._index = index
        self._size = (width, height)
        self._flush = flush
        self._cap = None
        self._open_lock = asyncio.Lock()

    def _open(self) -> None:
        import cv2

        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self._index, backend)
        if not cap.isOpened():
            cap.release()
            raise CapabilityError(NO_CAMERA, f"cannot open camera {self._index}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._size[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._size[1])
        self._cap = cap

    def _read(self) -> np.ndarray:
        # Drop buffered frames so the returned one reflects the scene now.
        frame = None
        for _ in range(self._flush + 1):
            ok, grabbed = self._cap.read()
            if ok:
                frame = grabbed
        if frame is None:
            raise CapabilityError(NO_CAMERA, "the camera returned no frame")
        return frame

    async def grab(self) -> np.ndarray:
        async with self._open_lock:
            if self._cap is None:
                await asyncio.to_thread(self._open)
        return await asyncio.to_thread(self._read)

    async def close(self) -> None:
        if self._cap is not None:
            await asyncio.to_thread(self._cap.release)
            self._cap = None
