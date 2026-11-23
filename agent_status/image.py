"""Decode one agent-supplied image into the 640x480 1bpp field."""

import base64
import io

import numpy as np
from PIL import Image

from visualizer.renderer import FIELD_HEIGHT, FIELD_WIDTH

MAX_PIXELS = 8_000_000


def image_mask(encoded: str) -> bytes:
    """Scale a PNG, JPEG, BMP, or WebP to the field and threshold it at 127."""
    try:
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.width < 1 or im.height < 1 or im.width * im.height > MAX_PIXELS:
                raise ValueError("dimensions")
            gray = im.convert("L").resize((FIELD_WIDTH, FIELD_HEIGHT), Image.Resampling.BOX)
    except Exception as exc:
        raise ValueError("image data is not a decodable PNG, JPEG, BMP, or WebP") from exc
    return (np.asarray(gray) > 127).astype(np.uint8).tobytes()
