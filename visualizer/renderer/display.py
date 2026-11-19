"""IrisGreen field / device adaptation constants for the POC-3 renderer.

The first-version field is a 640x480, origin-top-left, 1 bit-per-pixel
bitmap. Output arrays are uint8 with values in {0, 1} (not 0/255).
"""

FIELD_WIDTH = 640
FIELD_HEIGHT = 480
FIELD_ORIGIN = "top-left"
FIELD_BPP = 1
LIT = 1
OFF = 0
TARGET_FPS = 30


class DisplaySpec:
    """Device field description used by the Renderer."""

    width: int = FIELD_WIDTH
    height: int = FIELD_HEIGHT
    origin: str = FIELD_ORIGIN
    bpp: int = FIELD_BPP
    lit_value: int = LIT
    off_value: int = OFF

    def __init__(
        self,
        width: int = FIELD_WIDTH,
        height: int = FIELD_HEIGHT,
        origin: str = FIELD_ORIGIN,
        bpp: int = FIELD_BPP,
        lit_value: int = LIT,
        off_value: int = OFF,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("display width and height must be positive")
        if bpp != 1:
            raise ValueError("POC-3 renderer only supports 1bpp output")
        self.width = width
        self.height = height
        self.origin = origin
        self.bpp = bpp
        self.lit_value = lit_value
        self.off_value = off_value

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)
