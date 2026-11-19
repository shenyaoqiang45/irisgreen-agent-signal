"""High-contrast binary typography and lyric layout for a 1bpp laser field."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from visualizer.renderer.fonts import FontChoice, load_font, resolve_font

# 4x4 Bayer matrix for a simple 1bpp fade (not a photographic dither).
_BAYER4 = (
    np.array(
        [
            [0, 8, 2, 10],
            [12, 4, 14, 6],
            [3, 11, 1, 9],
            [15, 7, 13, 5],
        ],
        dtype=np.float64,
    )
    + 0.5
) / 16.0


def measure_text(text: str, font) -> tuple[int, int]:
    """Return (width, height) of ``text`` for the given PIL font."""
    image = Image.new("L", (1, 1), 0)
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return max(0, int(right - left)), max(0, int(bottom - top))


def fit_font(text: str, max_width: int, max_size: int, min_size: int = 16, choice: FontChoice | None = None):
    """Shrink the font until the text fits in ``max_width`` (or ``min_size``)."""
    info = choice or resolve_font()
    for size in range(max_size, min_size - 1, -2):
        font = load_font(size, info)
        width, height = measure_text(text, font)
        if width <= max_width or size == min_size:
            return font, width, height, size
    font = load_font(min_size, info)
    width, height = measure_text(text, font)
    return font, width, height, min_size


def rasterize_text(
    text: str,
    *,
    max_width: int,
    font_size: int,
    threshold: int = 128,
    choice: FontChoice | None = None,
) -> np.ndarray:
    """Render ``text`` to a tight uint8 {0,1} mask (high-contrast, no gray)."""
    if not text:
        return np.zeros((1, 1), dtype=np.uint8)
    font, width, height, _ = fit_font(text, max_width, font_size, choice=choice)
    # Padding avoids clipping glyph antialiasing before the binary threshold.
    pad = 4
    image = Image.new("L", (max(1, width + pad * 2), max(1, height + pad * 2)), 0)
    draw = ImageDraw.Draw(image)
    # textbbox origin can be negative for some fonts; offset by the bbox.
    left, top, _, _ = draw.textbbox((pad, pad), text, font=font)
    draw.text((pad + (pad - left), pad + (pad - top)), text, font=font, fill=255)
    array = np.asarray(image, dtype=np.uint8)
    binary = (array >= threshold).astype(np.uint8)
    rows = np.any(binary, axis=1)
    cols = np.any(binary, axis=0)
    if not rows.any() or not cols.any():
        return binary
    rmin, rmax = int(np.argmax(rows)), int(len(rows) - np.argmax(rows[::-1]))
    cmin, cmax = int(np.argmax(cols)), int(len(cols) - np.argmax(cols[::-1]))
    return binary[rmin:rmax, cmin:cmax]


def apply_fade(mask: np.ndarray, intensity: float, origin_y: int = 0, origin_x: int = 0) -> np.ndarray:
    """Fade a binary glyph mask with a Bayer threshold (readable 1bpp fade)."""
    if intensity <= 0.02:
        return np.zeros_like(mask)
    if intensity >= 0.99:
        return mask
    height, width = mask.shape
    yy, xx = np.ogrid[:height, :width]
    bayer = _BAYER4[(yy + origin_y) % 4, (xx + origin_x) % 4]
    return (mask.astype(np.uint8) & (intensity > bayer).astype(np.uint8)).astype(np.uint8)


def blit(
    frame: np.ndarray,
    mask: np.ndarray,
    center_x: int,
    center_y: int,
    *,
    intensity: float = 1.0,
    lit: int = 1,
) -> None:
    """OR a binary mask onto ``frame``, centered at (center_x, center_y)."""
    faded = apply_fade(mask, intensity, origin_y=center_y, origin_x=center_x)
    if faded.size == 0 or not faded.any():
        return
    mh, mw = faded.shape
    fh, fw = frame.shape
    x0 = int(center_x - mw // 2)
    y0 = int(center_y - mh // 2)
    x1 = x0 + mw
    y1 = y0 + mh
    sx0 = 0 if x0 >= 0 else -x0
    sy0 = 0 if y0 >= 0 else -y0
    sx1 = mw if x1 <= fw else mw - (x1 - fw)
    sy1 = mh if y1 <= fh else mh - (y1 - fh)
    dx0 = max(x0, 0)
    dy0 = max(y0, 0)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    region = frame[dy0 : dy0 + (sy1 - sy0), dx0 : dx0 + (sx1 - sx0)]
    stamp = faded[sy0:sy1, sx0:sx1].astype(bool)
    region[stamp] = lit
