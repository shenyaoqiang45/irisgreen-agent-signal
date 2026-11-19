"""Compose lyrics, beat pulse, and spectrum into one 640x480 1bpp frame.

The Renderer does not capture audio, run DSP, fetch lyrics, manage
player state, or talk to BLE. It only turns an evaluated visual state
plus a Scene layout into a binary field.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from visualizer.renderer.display import (
    FIELD_HEIGHT,
    FIELD_WIDTH,
    LIT,
    OFF,
    DisplaySpec,
)
from visualizer.renderer.draw import draw_bar, draw_hline, draw_ring
from visualizer.renderer.fonts import FontChoice, font_supports_cjk, resolve_font
from visualizer.renderer.typography import blit, rasterize_text

# Pulse ring: base radius / thickness, then expand with intensity.
_PULSE_RADIUS_MIN = 48.0
_PULSE_RADIUS_SPAN = 90.0
_PULSE_THICK_MIN = 2.0
_PULSE_THICK_SPAN = 7.0

_BAR_WIDTH = 72
_BAR_GAP = 36


class Renderer:
    """1bpp field renderer for the IrisGreen 640x480 laser-style display."""

    def __init__(
        self,
        display: DisplaySpec | None = None,
        *,
        font_choice: FontChoice | None = None,
    ) -> None:
        self.display = display or DisplaySpec()
        self.font_choice = font_choice if font_choice is not None else resolve_font()

    @property
    def supports_cjk(self) -> bool:
        return font_supports_cjk(self.font_choice)

    def empty_frame(self) -> np.ndarray:
        return np.full(self.display.shape, OFF, dtype=np.uint8)

    def render(self, state: Any, scene: Any | None = None) -> np.ndarray:
        """Render one combined frame.

        ``state`` is duck-typed (``FrameState`` or any object with
        ``lyric`` / ``pulse`` / ``spectrum``). ``scene`` supplies layout
        coordinates; a default karaoke layout is used when omitted.
        """
        frame = self.empty_frame()
        layout = scene or _DefaultLayout()
        self._draw_spectrum(frame, getattr(state, "spectrum", None), layout)
        self._draw_pulse(frame, getattr(state, "pulse", None), layout)
        self._draw_lyrics(frame, getattr(state, "lyric", None), layout)
        # Guarantee the contract even if a helper used a different dtype.
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)
        np.clip(frame, 0, 1, out=frame)
        return frame

    def _draw_lyrics(self, frame: np.ndarray, lyric: Any, layout: Any) -> None:
        if lyric is None:
            return
        text = str(getattr(lyric, "text", "") or "")
        if not text:
            return
        # Glyphs stay solid while the line is active so a 1bpp laser field
        # stays readable. The fade envelope drives the underline length,
        # not a photographic dither of the type.
        intensity = float(getattr(lyric, "intensity", 1.0))
        max_width = int(getattr(layout, "lyric_max_width", FIELD_WIDTH - 40))
        font_size = int(getattr(layout, "lyric_font_size", 44))
        mask = rasterize_text(
            text,
            max_width=max_width,
            font_size=font_size,
            choice=self.font_choice,
        )
        cx = int(getattr(layout, "lyric_center_x", FIELD_WIDTH // 2))
        cy = int(getattr(layout, "lyric_center_y", 200))
        blit(frame, mask, cx, cy, intensity=1.0, lit=LIT)
        underline_w = max(8, int(max_width * 0.35 * min(1.0, max(intensity, 0.08))))
        underline_y = min(frame.shape[0] - 1, cy + mask.shape[0] // 2 + 8)
        draw_hline(
            frame,
            underline_y,
            cx - underline_w // 2,
            cx + underline_w // 2,
            lit=LIT,
        )

    def _draw_pulse(self, frame: np.ndarray, pulse: Any, layout: Any) -> None:
        if pulse is None:
            return
        intensity = float(getattr(pulse, "intensity", 0.0))
        if intensity <= 0:
            return
        cx = int(getattr(layout, "pulse_center_x", FIELD_WIDTH // 2))
        cy = int(getattr(layout, "pulse_center_y", 200))
        radius = _PULSE_RADIUS_MIN + _PULSE_RADIUS_SPAN * intensity
        thickness = _PULSE_THICK_MIN + _PULSE_THICK_SPAN * intensity
        draw_ring(frame, cx, cy, radius, thickness, lit=LIT)

    def _draw_spectrum(self, frame: np.ndarray, spectrum: Any, layout: Any) -> None:
        if spectrum is None:
            return
        bands = (
            float(getattr(spectrum, "bass", 0.0)),
            float(getattr(spectrum, "mid", 0.0)),
            float(getattr(spectrum, "treble", 0.0)),
        )
        baseline = int(getattr(layout, "spectrum_baseline_y", 450))
        max_height = int(getattr(layout, "spectrum_max_height", 120))
        total = 3 * _BAR_WIDTH + 2 * _BAR_GAP
        x0 = (self.display.width - total) // 2
        draw_hline(frame, baseline, x0, x0 + total, lit=LIT)
        for index, value in enumerate(bands):
            value = 0.0 if value < 0 else 1.0 if value > 1 else value
            height = int(round(value * max_height))
            if value > 0 and height < 1:
                height = 1
            x = x0 + index * (_BAR_WIDTH + _BAR_GAP)
            draw_bar(frame, x, baseline, _BAR_WIDTH, height, lit=LIT)


class _DefaultLayout:
    lyric_center_x = FIELD_WIDTH // 2
    lyric_center_y = 200
    pulse_center_x = FIELD_WIDTH // 2
    pulse_center_y = 200
    spectrum_baseline_y = 450
    spectrum_max_height = 120
    lyric_max_width = 600
    lyric_font_size = 44
