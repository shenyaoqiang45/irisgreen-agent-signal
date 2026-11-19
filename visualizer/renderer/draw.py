"""Simple 1bpp primitives: rings (beat pulse) and bars (spectrum)."""

from __future__ import annotations

import numpy as np


def draw_ring(
    frame: np.ndarray,
    center_x: int,
    center_y: int,
    radius: float,
    thickness: float,
    *,
    lit: int = 1,
) -> None:
    """Draw a binary ring. Coordinates are in field pixels, origin top-left."""
    if radius <= 0 or thickness <= 0:
        return
    height, width = frame.shape
    inner = max(0.0, radius - thickness)
    # Bound the work to a loose bounding box.
    x0 = max(0, int(center_x - radius - 1))
    x1 = min(width, int(center_x + radius + 2))
    y0 = max(0, int(center_y - radius - 1))
    y1 = min(height, int(center_y + radius + 2))
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    dist = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2)
    mask = (dist <= radius) & (dist >= inner)
    region = frame[y0:y1, x0:x1]
    region[mask] = lit


def draw_bar(
    frame: np.ndarray,
    x: int,
    baseline_y: int,
    width: int,
    height: int,
    *,
    lit: int = 1,
) -> None:
    """Fill a rectangle growing upward from ``baseline_y`` (exclusive top)."""
    if width <= 0 or height <= 0:
        return
    fh, fw = frame.shape
    x0 = max(0, int(x))
    x1 = min(fw, int(x + width))
    y1 = min(fh, max(0, int(baseline_y)))
    y0 = max(0, y1 - int(height))
    if x1 <= x0 or y1 <= y0:
        return
    frame[y0:y1, x0:x1] = lit


def draw_hline(frame: np.ndarray, y: int, x0: int, x1: int, *, lit: int = 1) -> None:
    fh, fw = frame.shape
    if y < 0 or y >= fh:
        return
    a = max(0, min(int(x0), int(x1)))
    b = min(fw, max(int(x0), int(x1)))
    if b <= a:
        return
    frame[y, a:b] = lit
