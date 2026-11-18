"""Camera <-> projector coordinate mapping (a planar homography)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np

PROJ_WIDTH = 640
PROJ_HEIGHT = 480

SCHEMA = "irisgreen.calibration/1"


def homography_is_sane(H: np.ndarray, min_area_px: float = 1000.0) -> bool:
    """True if H maps the projector field to a plausible camera quad.

    A fit can have tiny residuals and still be garbage (e.g. all dots detected
    on one moving object). Sane means: the perspective divisor has one sign
    over the field, and the mapped corners form a convex quad of real area.
    """
    H = np.asarray(H, dtype=np.float64)
    if H.shape != (3, 3) or not np.isfinite(H).all():
        return False
    corners = np.array(
        [[0, 0], [PROJ_WIDTH - 1, 0], [PROJ_WIDTH - 1, PROJ_HEIGHT - 1], [0, PROJ_HEIGHT - 1]],
        dtype=np.float64,
    )
    w = H[2, 0] * corners[:, 0] + H[2, 1] * corners[:, 1] + H[2, 2]
    if not ((w > 1e-9).all() or (w < -1e-9).all()):
        return False
    quad = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), H).reshape(-1, 2)
    if not np.isfinite(quad).all():
        return False
    edges = np.roll(quad, -1, axis=0) - quad
    turns = edges[:, 0] * np.roll(edges, -1, axis=0)[:, 1] - edges[:, 1] * np.roll(edges, -1, axis=0)[:, 0]
    convex = bool((turns > 0).all() or (turns < 0).all())
    area = 0.5 * abs(float(np.dot(quad[:, 0], np.roll(quad[:, 1], -1)) - np.dot(quad[:, 1], np.roll(quad[:, 0], -1))))
    return convex and area >= min_area_px


def solve_homography(
    records: list[dict],
    ransac_thresh: float = 3.0,
) -> tuple[np.ndarray, dict]:
    """Solve the projector->camera homography from point pairs.

    Each record is {"proj": [x, y], "cam": [x, y] | None}; records without a
    camera point are ignored. Returns (H, stats). Raises ValueError if there
    are too few points or the result is geometrically implausible.
    """
    pairs = [(r["proj"], r["cam"]) for r in records if r.get("cam")]
    if len(pairs) < 4:
        raise ValueError(f"need >= 4 valid point pairs, got {len(pairs)}")
    proj = np.array([p for p, _ in pairs], dtype=np.float64)
    cam = np.array([c for _, c in pairs], dtype=np.float64)

    H, mask = cv2.findHomography(
        proj.reshape(-1, 1, 2), cam.reshape(-1, 1, 2), cv2.RANSAC, ransac_thresh
    )
    if H is None:
        raise ValueError("findHomography failed (points degenerate?)")
    inliers = mask.ravel().astype(bool)
    # Least-squares refit on the inliers only.
    if int(inliers.sum()) >= 4:
        H = cv2.findHomography(
            proj[inliers].reshape(-1, 1, 2), cam[inliers].reshape(-1, 1, 2), 0
        )[0]
    if H is None or not homography_is_sane(H):
        raise ValueError(
            "the solved mapping is geometrically implausible; the scene probably "
            "changed during calibration (keep the camera, projector and wall still)"
        )

    pred = cv2.perspectiveTransform(proj.reshape(-1, 1, 2), H).reshape(-1, 2)
    err = np.linalg.norm(pred - cam, axis=1)
    stats = {
        "total": len(pairs),
        "inliers": int(inliers.sum()),
        "outliers": [i for i, ok in enumerate(inliers) if not ok],
        "err_mean": float(err[inliers].mean()) if inliers.any() else float(err.mean()),
        "err_max": float(err[inliers].max()) if inliers.any() else float(err.max()),
        "err_all_mean": float(err.mean()),
    }
    return H, stats


@dataclass
class Calibration:
    """A solved projector<->camera homography."""

    H: np.ndarray  # projector pixel -> camera pixel
    stats: dict | None = None

    @property
    def H_inv(self) -> np.ndarray:
        return np.linalg.inv(self.H)

    @staticmethod
    def _map(pts, M: np.ndarray) -> np.ndarray:
        a = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(a, M).reshape(-1, 2)

    def proj_to_cam(self, pts) -> np.ndarray:
        return self._map(pts, self.H)

    def cam_to_proj(self, pts) -> np.ndarray:
        return self._map(pts, self.H_inv)

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "proj_size": [PROJ_WIDTH, PROJ_HEIGHT],
            "H": np.asarray(self.H, dtype=np.float64).tolist(),
            "stats": self.stats or {},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Calibration":
        if data.get("schema") != SCHEMA:
            raise ValueError(f"unsupported calibration schema: {data.get('schema')}")
        H = np.asarray(data["H"], dtype=np.float64)
        if H.shape != (3, 3) or not np.isfinite(H).all() or abs(np.linalg.det(H)) < 1e-12:
            raise ValueError("calibration matrix is not a valid homography")
        return cls(H=H, stats=data.get("stats") or None)

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(self.to_dict(), stream, indent=2)

    @classmethod
    def load(cls, path: str) -> "Calibration":
        with open(path, encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))


def in_projection_field(points, margin: float = 0.0) -> bool:
    """True if every projector-space point lies inside the 640x480 field."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    return bool(
        np.isfinite(pts).all()
        and (pts[:, 0] >= margin).all() and (pts[:, 0] <= PROJ_WIDTH - 1 - margin).all()
        and (pts[:, 1] >= margin).all() and (pts[:, 1] <= PROJ_HEIGHT - 1 - margin).all()
    )


def camera_point_to_projector(calib: Calibration, point) -> tuple[float, float]:
    """Map one camera pixel to a projector pixel; raise if it is outside the field."""
    mapped = calib.cam_to_proj(point)[0]
    if not in_projection_field(mapped):
        raise ValueError(
            f"camera point {tuple(float(v) for v in np.ravel(point))} maps outside "
            f"the projection field: ({mapped[0]:.1f}, {mapped[1]:.1f})"
        )
    return float(mapped[0]), float(mapped[1])


def place_in_camera_rect(
    bw: np.ndarray,
    calib: Calibration,
    rect: tuple[float, float, float, float],
    padding: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    """Place 1bpp content inside a camera-view rectangle (x0, y0, x1, y1).

    The source aspect ratio is preserved (contain fit), then the fitted camera
    rectangle is mapped back to projector coordinates through the calibration.
    Returns the 640x480 projector bitmap and its projector-space quad.
    """
    source = np.asarray(bw, dtype=np.uint8)
    if source.ndim != 2 or source.shape[0] < 2 or source.shape[1] < 2:
        raise ValueError(f"expected a 2D image at least 2x2, got {source.shape}")
    x0, y0, x1, y1 = (float(v) for v in rect)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"invalid camera rectangle: {rect}")
    if not 0.0 <= padding < 0.5:
        raise ValueError(f"padding must be in [0, 0.5), got {padding}")

    inset_x = (x1 - x0) * padding
    inset_y = (y1 - y0) * padding
    x0, x1 = x0 + inset_x, x1 - inset_x
    y0, y1 = y0 + inset_y, y1 - inset_y
    target_w, target_h = x1 - x0, y1 - y0
    source_aspect = source.shape[1] / source.shape[0]
    if target_w / target_h > source_aspect:
        fitted_w = target_h * source_aspect
        x0 += (target_w - fitted_w) / 2
        x1 = x0 + fitted_w
    else:
        fitted_h = target_w / source_aspect
        y0 += (target_h - fitted_h) / 2
        y1 = y0 + fitted_h

    camera_quad = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)
    projector_quad = calib.cam_to_proj(camera_quad)
    if not in_projection_field(projector_quad):
        raise ValueError(
            "camera rectangle extends outside the calibrated projection field: "
            f"{projector_quad.round(1).tolist()}"
        )

    h, w = source.shape
    source_quad = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    transform = cv2.getPerspectiveTransform(source_quad, projector_quad.astype(np.float32))
    placed = cv2.warpPerspective(
        source, transform, (PROJ_WIDTH, PROJ_HEIGHT),
        flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    return (placed > 0).astype(np.uint8), projector_quad


def render_camera_polygon(
    polygon,
    calib: Calibration,
    camera_size: tuple[int, int],
    *,
    mode: str = "shape",
    stroke_px: int = 3,
) -> np.ndarray:
    """Render a camera-space polygon as a 640x480 projector bitmap.

    mode "shape" fills the polygon; "stroke" draws its outline `stroke_px` wide
    (measured in camera pixels). Every vertex must land inside the field.
    """
    if mode not in ("shape", "stroke"):
        raise ValueError(f"unsupported mode: {mode}")
    pts = np.asarray(polygon, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        raise ValueError("polygon needs at least 3 points")
    if not in_projection_field(calib.cam_to_proj(pts)):
        raise ValueError("part of the polygon is outside the projection field")

    cam_w, cam_h = camera_size
    camera_mask = np.zeros((cam_h, cam_w), dtype=np.uint8)
    poly = np.rint(pts).astype(np.int32)
    if mode == "shape":
        cv2.fillPoly(camera_mask, [poly], 1)
    else:
        cv2.polylines(camera_mask, [poly], True, 1, max(1, int(stroke_px)))
    mask = cv2.warpPerspective(
        camera_mask, calib.H_inv, (PROJ_WIDTH, PROJ_HEIGHT),
        flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    if not mask.any():
        raise ValueError("polygon renders to an empty mask")
    return (mask > 0).astype(np.uint8)
