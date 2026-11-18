"""Locate the projected laser spot in a camera frame."""

from __future__ import annotations

import cv2
import numpy as np


def _greenness(frame: np.ndarray) -> np.ndarray:
    """How much greener a pixel is than red/blue. Laser green saturates G."""
    b, g, r = cv2.split(frame.astype(np.int16))
    return g - np.maximum(b, r)


def detect_dot(
    frame: np.ndarray,
    bg: np.ndarray | None = None,
    threshold: int = 40,
    min_area: int = 6,
    border: int = 24,
) -> tuple[tuple[float, float] | None, int]:
    """Locate the laser spot in a BGR frame.

    Returns ((cx, cy), area) with a score-weighted subpixel centroid, or
    (None, area_of_largest_candidate) when nothing clears the thresholds.

    The score against the background frame (projection off) combines:
      - greenness gain, for unsaturated green light
      - green-channel brightness gain, because a bright dot saturates the
        sensor to white, where greenness collapses to ~0
    Blobs must be compact (fill >= 0.35, elongation <= 3): reflections and
    edge exposure drift form long strips or sparse blobs. `border` pixels at
    the frame edge are ignored.
    """
    if bg is not None:
        score = _greenness(frame) - _greenness(bg)
        dg = frame.astype(np.int16)[..., 1] - bg.astype(np.int16)[..., 1]
        score = score + np.clip(dg, 0, None)
    else:
        score = _greenness(frame)
    mask = (score > threshold).astype(np.uint8)
    if border > 0:
        mask[:border, :] = 0
        mask[-border:, :] = 0
        mask[:, :border] = 0
        mask[:, -border:] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n < 2:
        return None, 0
    largest_area = int(stats[1:, cv2.CC_STAT_AREA].max())
    candidates = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        width = int(stats[i, cv2.CC_STAT_WIDTH])
        height = int(stats[i, cv2.CC_STAT_HEIGHT])
        fill = area / max(1, width * height)
        elongation = max(width, height) / max(1, min(width, height))
        if area >= min_area and fill >= 0.35 and elongation <= 3.0:
            candidates.append((area, i))
    if not candidates:
        return None, largest_area
    area, idx = max(candidates)
    comp = labels == idx
    w = np.clip(score, 0, None).astype(np.float64) * comp
    total = float(w.sum())
    if total <= 0:
        return (float(cents[idx][0]), float(cents[idx][1])), area
    ys, xs = np.nonzero(comp)
    cx = float((xs * w[comp]).sum() / total)
    cy = float((ys * w[comp]).sum() / total)
    return (cx, cy), area
