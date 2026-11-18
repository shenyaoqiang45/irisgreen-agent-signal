"""Reference :class:`Measurer`: template matching in a window around the previous box.

Dependency-free baseline so tracking works out of the box. Swap in a stronger
appearance tracker (anything implementing ``Measurer``) without touching the
rest of the pipeline.
"""

from __future__ import annotations

import cv2
import numpy as np

from .single_object import BBox, BoxMeasurement


class TemplateMeasurer:
    def __init__(self, search_margin: float = 0.75, update_rate: float = 0.1) -> None:
        """search_margin: extra search area as a fraction of box size per side.
        update_rate: blend of the matched patch into the template (0 = fixed template).
        """
        self.search_margin = float(search_margin)
        self.update_rate = float(update_rate)
        self.reset()

    def reset(self) -> None:
        self.template: np.ndarray | None = None
        self.bbox: BBox | None = None
        self._previous: tuple[np.ndarray, BBox] | None = None

    @staticmethod
    def _gray(frame: np.ndarray) -> np.ndarray:
        return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def start(self, frame: np.ndarray, bbox: BBox) -> BoxMeasurement:
        gray = self._gray(frame)
        h, w = gray.shape
        x, y, bw, bh = (int(round(v)) for v in bbox)
        x, y = max(0, x), max(0, y)
        bw, bh = min(bw, w - x), min(bh, h - y)
        if bw < 8 or bh < 8:
            raise ValueError("box is too small or outside the frame")
        self.template = gray[y:y + bh, x:x + bw].astype(np.float32)
        self.bbox = (float(x), float(y), float(bw), float(bh))
        self._previous = None
        return BoxMeasurement(self.bbox, 1.0)

    def track(self, frame: np.ndarray) -> BoxMeasurement:
        if self.template is None or self.bbox is None:
            raise RuntimeError("measurer not started")
        self._previous = (self.template, self.bbox)
        gray = self._gray(frame).astype(np.float32)
        h, w = gray.shape
        x, y, bw, bh = self.bbox
        mx, my = bw * self.search_margin, bh * self.search_margin
        sx0, sy0 = int(max(0, x - mx)), int(max(0, y - my))
        sx1, sy1 = int(min(w, x + bw + mx)), int(min(h, y + bh + my))
        window = gray[sy0:sy1, sx0:sx1]
        th, tw = self.template.shape
        if window.shape[0] < th or window.shape[1] < tw:
            return BoxMeasurement(self.bbox, 0.0)
        result = cv2.matchTemplate(window, self.template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        nx, ny = float(sx0 + loc[0]), float(sy0 + loc[1])
        self.bbox = (nx, ny, float(tw), float(th))
        patch = gray[int(ny):int(ny) + th, int(nx):int(nx) + tw]
        if self.update_rate > 0 and score > 0.7 and patch.shape == self.template.shape:
            self.template = (1 - self.update_rate) * self.template + self.update_rate * patch
        return BoxMeasurement(self.bbox, float(max(0.0, score)))

    def revert(self) -> None:
        """Undo the last `track` when its score was rejected."""
        if self._previous is not None:
            self.template, self.bbox = self._previous
            self._previous = None
