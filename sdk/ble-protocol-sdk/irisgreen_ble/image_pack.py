"""640x480 1bpp image packing for the IrisGreen data stream.

Payload layout (verified against a real-device BMP in the IrisLoop project):
    1. mirror horizontally and flip vertically (device reads BMP bottom-up)
    2. row-major bit flatten, 8 pixels per byte, MSB first -> 38400 bytes
    3. prepend the 62-byte BMP header (14 file + 40 DIB + 8 palette)
       -> 38462 bytes total

The spreadsheet's "124-byte header" is wrong; it is 62 bytes. Only packing
lives here. Binarization algorithms (otsu, dithering, edges) belong to the
algorithms layer.
"""

from __future__ import annotations

import numpy as np

WIDTH = 640
HEIGHT = 480
ROW_BYTES = WIDTH // 8           # 80
DATA_BYTES = ROW_BYTES * HEIGHT  # 38400
HEAD_BYTES = 62
STREAM_BYTES = HEAD_BYTES + DATA_BYTES  # 38462

# 640x480, 1bpp, data_offset=62, size=38400
BMP_HEAD = bytes.fromhex(
    "424D3E960000000000003E0000002800000080020000E00100000100010000"
    "00000000960000120B0000120B0000000000000000000000000000FFFFFF00"
)


def binarize(gray: np.ndarray, threshold: int = 127) -> np.ndarray:
    """Fixed-threshold gray -> {0,1} image (device-verified default)."""
    return (np.asarray(gray) > threshold).astype(np.uint8)


def pack(bw: np.ndarray) -> bytes:
    """Binary 480x640 image -> 38400-byte device payload."""
    if bw.shape != (HEIGHT, WIDTH):
        raise ValueError(f"expected {HEIGHT}x{WIDTH}, got {bw.shape}")
    a = np.flipud(np.fliplr(bw.astype(np.uint8)))
    bits = a.reshape(-1).reshape(-1, 8)
    weights = (1 << np.arange(7, -1, -1)).astype(np.uint8)
    return (bits * weights).sum(axis=1).astype(np.uint8).tobytes()


def build_stream(bw: np.ndarray) -> bytes:
    """62-byte BMP header + 38400-byte payload = 38462 bytes."""
    return BMP_HEAD + pack(bw)


def unpack(payload: bytes) -> np.ndarray:
    """Inverse of `pack`/`build_stream`: device payload -> binary 480x640 image."""
    data = bytes(payload)
    if len(data) == STREAM_BYTES:
        data = data[HEAD_BYTES:]
    if len(data) != DATA_BYTES:
        raise ValueError(f"expected {DATA_BYTES} or {STREAM_BYTES} bytes, got {len(data)}")
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    return bits[::-1].reshape(HEIGHT, WIDTH).copy()


def chunk(payload: bytes, size: int) -> list[bytes]:
    """Split a stream into writes of at most `size` bytes."""
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [payload[i : i + size] for i in range(0, len(payload), size)]
