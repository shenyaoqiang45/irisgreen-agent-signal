"""Gray image -> 1bpp conversion for the laser projector.

The device shows binary pixels only, so how an image is binarized is an
artistic and perceptual choice, kept here and out of the protocol layer.
"""

from __future__ import annotations

import cv2
import numpy as np


def binarize(gray: np.ndarray, threshold: int = 127) -> np.ndarray:
    return (np.asarray(gray) > threshold).astype(np.uint8)


def binarize_otsu(gray: np.ndarray) -> np.ndarray:
    """Otsu adaptive threshold, clamped to 40..220.

    A fixed 127 shatters coloured or gradient input; Otsu picks the split from
    the histogram. Near-uniform frames give a degenerate threshold, hence the clamp.
    """
    g = np.asarray(gray)
    t, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    t = float(np.clip(t, 40, 220))
    return (g > t).astype(np.uint8)


def dither_fs(gray: np.ndarray, gamma: float = 0.65, black_floor: float = 32.0) -> np.ndarray:
    """Floyd-Steinberg dithering: fake grayscale on 1bpp.

    gamma < 1 pre-brightens mid-tones: the MEMS laser spreads each lit pixel
    into its dark neighbours, so a 50% dot field reads dimmer than a solid
    block. `black_floor` cuts near-black codec noise through a soft knee
    (zero below floor/2, quadratic blend up to floor*1.5) so it is not lifted
    into stray dots. gamma=1.0 disables the boost.
    """
    g = np.asarray(gray, dtype=np.float32)
    if black_floor > 0:
        lo, hi = black_floor * 0.5, black_floor * 1.5
        knee = np.clip((g - lo) / (hi - lo), 0.0, 1.0)
        g = g * knee * knee
    if gamma != 1.0:
        g = 255.0 * np.power(np.clip(g / 255.0, 0.0, 1.0), gamma)
    g = g.copy()
    h, w = g.shape
    out = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            old = g[y, x]
            new = 255.0 if old > 127 else 0.0
            out[y, x] = 1 if new > 0 else 0
            err = old - new
            if x + 1 < w:
                g[y, x + 1] += err * 7.0 / 16
            if y + 1 < h:
                if x > 0:
                    g[y + 1, x - 1] += err * 3.0 / 16
                g[y + 1, x] += err * 5.0 / 16
                if x + 1 < w:
                    g[y + 1, x + 1] += err * 1.0 / 16
    return out


def edge_lines(gray: np.ndarray, *, dilate_px: int = 2) -> np.ndarray:
    """Line-art mode: smoothed Canny edges, dilated to survive MEMS scanning."""
    g = np.asarray(gray)
    sm = cv2.bilateralFilter(g, 7, 50, 50)
    edges = cv2.Canny(sm, 60, 160)
    if dilate_px > 0:
        k = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1, dilate_px * 2 + 1)
        )
        edges = cv2.dilate(edges, k)
    return (edges > 0).astype(np.uint8)


MODES = ("threshold", "threshold_inv", "otsu", "dither", "dither_flat", "edges")


def to_1bpp(gray: np.ndarray, mode: str = "threshold") -> np.ndarray:
    """Unified gray -> 1bpp conversion.

    threshold      fixed 127 (device-verified default, silhouette idiom)
    threshold_inv  inverted fixed 127 (negative idiom)
    otsu           adaptive threshold
    dither         Floyd-Steinberg halftone with gamma boost
    dither_flat    Floyd-Steinberg without gamma boost
    edges          dilated Canny line art
    """
    if mode == "threshold":
        return binarize(gray)
    if mode == "threshold_inv":
        return 1 - binarize(gray)
    if mode == "otsu":
        return binarize_otsu(gray)
    if mode == "dither":
        return dither_fs(gray)
    if mode == "dither_flat":
        return dither_fs(gray, gamma=1.0)
    if mode == "edges":
        return edge_lines(gray)
    raise ValueError(f"unknown mode: {mode} (expected one of {', '.join(MODES)})")
