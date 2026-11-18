"""Projector <-> camera calibration by projecting a grid of dots and finding each one.

The procedure is device-independent: it drives two injected coroutines,
``show_dot`` (display a 640x480 mask) and ``grab_frame`` (return a camera
frame), so it works with a real device, a simulator, or a recorded set.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

import cv2
import numpy as np

from irisgreen_detection import detect_dot
from irisgreen_mapping import PROJ_HEIGHT, PROJ_WIDTH, Calibration, solve_homography

ShowMask = Callable[[np.ndarray], Awaitable[None]]
GrabFrame = Callable[[], Awaitable[np.ndarray]]


class CalibrationError(RuntimeError):
    """Calibration could not produce a trustworthy mapping."""


@dataclass
class CalibrationResult:
    calibration: Calibration
    records: list[dict]
    stats: dict


def grid_points(cols: int, rows: int, margin: float = 0.12) -> list[tuple[float, float]]:
    """Row-major grid of projector coordinates, inset by `margin` (fraction)."""
    xs = np.linspace(PROJ_WIDTH * margin, PROJ_WIDTH * (1 - margin), cols)
    ys = np.linspace(PROJ_HEIGHT * margin, PROJ_HEIGHT * (1 - margin), rows)
    return [(float(x), float(y)) for y in ys for x in xs]


def default_test_points() -> list[tuple[float, float]]:
    """Five points (quarter-grid corners + centre), disjoint from the default grid."""
    return [
        (PROJ_WIDTH * 0.25, PROJ_HEIGHT * 0.25),
        (PROJ_WIDTH * 0.75, PROJ_HEIGHT * 0.25),
        (PROJ_WIDTH * 0.5, PROJ_HEIGHT * 0.5),
        (PROJ_WIDTH * 0.25, PROJ_HEIGHT * 0.75),
        (PROJ_WIDTH * 0.75, PROJ_HEIGHT * 0.75),
    ]


def make_dot_image(x: float, y: float, radius: int = 12) -> np.ndarray:
    """640x480 1bpp image with a single filled dot at (x, y)."""
    img = np.zeros((PROJ_HEIGHT, PROJ_WIDTH), dtype=np.uint8)
    cv2.circle(img, (int(round(x)), int(round(y))), radius, 1, -1)
    return img


async def _capture(show_dot: ShowMask, grab_frame: GrabFrame, mask: np.ndarray, settle_s: float):
    await show_dot(mask)
    await asyncio.sleep(settle_s)
    return await grab_frame()


async def calibrate(
    show_dot: ShowMask,
    grab_frame: GrabFrame,
    *,
    cols: int = 4,
    rows: int = 3,
    margin: float = 0.12,
    radius: int = 12,
    settle_s: float = 0.4,
    max_mean_error_px: float = 6.0,
    min_inlier_ratio: float = 0.7,
) -> CalibrationResult:
    """Project a dot grid and solve the projector->camera homography.

    Raises CalibrationError if fewer than half of the dots are found, too few
    of the found dots agree with the fit (`min_inlier_ratio`; RANSAC can fit
    four random points exactly, so error alone is not enough), or the mean
    inlier error exceeds `max_mean_error_px` camera pixels.
    """
    if cols < 2 or rows < 2:
        raise ValueError("grid needs at least 2 columns and 2 rows")

    background = await _capture(
        show_dot, grab_frame, np.zeros((PROJ_HEIGHT, PROJ_WIDTH), np.uint8), settle_s
    )
    records: list[dict] = []
    for x, y in grid_points(cols, rows, margin):
        frame = await _capture(show_dot, grab_frame, make_dot_image(x, y, radius), settle_s)
        found, area = detect_dot(frame, background)
        records.append({
            "proj": [x, y],
            "cam": [found[0], found[1]] if found else None,
            "area": area,
        })

    detected = sum(1 for r in records if r["cam"])
    if detected < max(4, len(records) // 2):
        raise CalibrationError(
            f"found only {detected} of {len(records)} dots; check camera exposure, "
            "focus and that the projection is visible"
        )
    try:
        H, stats = solve_homography(records)
    except ValueError as exc:
        raise CalibrationError(str(exc)) from exc
    if stats["inliers"] < min_inlier_ratio * stats["total"]:
        raise CalibrationError(
            f"only {stats['inliers']} of {stats['total']} detected dots agree on one mapping; "
            "the camera or projector probably moved, or something else is glowing green"
        )
    if stats["err_mean"] > max_mean_error_px:
        raise CalibrationError(
            f"mapping error too high: mean {stats['err_mean']:.1f}px "
            f"(limit {max_mean_error_px:.1f}px)"
        )
    stats["detected"] = detected
    stats["grid"] = [cols, rows]
    return CalibrationResult(Calibration(H=H, stats=stats), records, stats)


async def verify(
    calibration: Calibration,
    show_dot: ShowMask,
    grab_frame: GrabFrame,
    *,
    points: list[tuple[float, float]] | None = None,
    radius: int = 12,
    settle_s: float = 0.4,
) -> dict:
    """Project fresh points and measure how far each lands from its prediction (camera px)."""
    background = await _capture(
        show_dot, grab_frame, np.zeros((PROJ_HEIGHT, PROJ_WIDTH), np.uint8), settle_s
    )
    errors: list[float | None] = []
    for x, y in points or default_test_points():
        frame = await _capture(show_dot, grab_frame, make_dot_image(x, y, radius), settle_s)
        found, _ = detect_dot(frame, background)
        if found is None:
            errors.append(None)
            continue
        predicted = calibration.proj_to_cam([x, y])[0]
        errors.append(float(np.hypot(found[0] - predicted[0], found[1] - predicted[1])))
    valid = [e for e in errors if e is not None]
    return {
        "points": len(errors),
        "detected": len(valid),
        "errors_px": errors,
        "mean_px": float(np.mean(valid)) if valid else None,
        "max_px": float(np.max(valid)) if valid else None,
    }
