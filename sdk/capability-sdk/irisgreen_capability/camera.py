"""Camera abstraction. The capability layer only needs BGR frames."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import numpy as np


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
    """A USB / built-in camera through OpenCV."""

    def __init__(self, index: int = 0, width: int = 1280, height: int = 720, flush: int = 4):
        import cv2

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(index, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open camera {index}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._flush = flush

    def _read(self) -> np.ndarray:
        # Drop buffered frames so the returned one reflects the scene now.
        frame = None
        for _ in range(self._flush + 1):
            ok, grabbed = self._cap.read()
            if ok:
                frame = grabbed
        if frame is None:
            raise RuntimeError("camera returned no frame")
        return frame

    async def grab(self) -> np.ndarray:
        return await asyncio.to_thread(self._read)

    async def close(self) -> None:
        self._cap.release()
