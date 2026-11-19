"""1bpp typography, layout, and frame generation.

This package must stay free of audio capture, DSP, lyric fetching,
player-state management, and BLE / Capability SDK imports.
"""

from visualizer.renderer.display import (
    FIELD_BPP,
    FIELD_HEIGHT,
    FIELD_ORIGIN,
    FIELD_WIDTH,
    LIT,
    OFF,
    TARGET_FPS,
    DisplaySpec,
)
from visualizer.renderer.fonts import FontChoice, font_supports_cjk, resolve_font
from visualizer.renderer.frame import Renderer

__all__ = [
    "FIELD_BPP",
    "FIELD_HEIGHT",
    "FIELD_ORIGIN",
    "FIELD_WIDTH",
    "LIT",
    "OFF",
    "TARGET_FPS",
    "DisplaySpec",
    "FontChoice",
    "Renderer",
    "font_supports_cjk",
    "resolve_font",
]
