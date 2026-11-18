"""Perception algorithms: laser-spot detection, VLM grounding, 1bpp conversion."""

from .binarize import MODES, to_1bpp
from .grounding import GROUND_PROMPT, extract_json_value, refine_outline, regions_from_reply
from .laser import detect_dot

__all__ = [
    "GROUND_PROMPT",
    "MODES",
    "detect_dot",
    "extract_json_value",
    "refine_outline",
    "regions_from_reply",
    "to_1bpp",
]
