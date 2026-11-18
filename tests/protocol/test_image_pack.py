import json
from pathlib import Path

import numpy as np
import pytest

from irisgreen_ble import image_pack as I

VECTORS = json.loads(
    (Path(__file__).parents[1] / "cross-platform" / "protocol-vectors.json").read_text()
)


def test_sizes():
    assert I.HEAD_BYTES == len(I.BMP_HEAD) == 62
    bw = np.zeros((I.HEIGHT, I.WIDTH), dtype=np.uint8)
    assert len(I.pack(bw)) == I.DATA_BYTES == 38400
    assert len(I.build_stream(bw)) == I.STREAM_BYTES == 38462


def test_bmp_header_matches_geometry():
    assert I.BMP_HEAD[:2] == b"BM"
    assert int.from_bytes(I.BMP_HEAD[2:6], "little") == I.STREAM_BYTES
    assert int.from_bytes(I.BMP_HEAD[10:14], "little") == I.HEAD_BYTES
    assert int.from_bytes(I.BMP_HEAD[18:22], "little") == I.WIDTH
    assert int.from_bytes(I.BMP_HEAD[22:26], "little") == I.HEIGHT


def test_pack_orientation_and_bit_order():
    # Top-left pixel lands in the last byte (180 degree rotation), MSB-first bit order.
    bw = np.zeros((I.HEIGHT, I.WIDTH), dtype=np.uint8)
    bw[0, 0] = 1
    data = I.pack(bw)
    assert data[-1] == 0x01
    assert sum(data) == 1

    bw = np.zeros((I.HEIGHT, I.WIDTH), dtype=np.uint8)
    bw[I.HEIGHT - 1, I.WIDTH - 1] = 1
    assert I.pack(bw)[0] == 0x80


def test_pack_golden_vectors():
    for vec in VECTORS["image"]["pack"]:
        bw = np.zeros((I.HEIGHT, I.WIDTH), dtype=np.uint8)
        for r, c in vec["pixels"]:
            bw[r, c] = 1
        assert I.pack(bw)[vec["byte_index"]] == int(vec["value"], 16), vec["name"]
        assert sum(I.pack(bw)) == int(vec["value"], 16)
    assert I.BMP_HEAD.hex().upper() == VECTORS["image"]["bmp_head"].upper()


def test_unpack_roundtrip():
    rng = np.random.default_rng(1)
    bw = (rng.random((I.HEIGHT, I.WIDTH)) > 0.5).astype(np.uint8)
    assert np.array_equal(I.unpack(I.pack(bw)), bw)
    assert np.array_equal(I.unpack(I.build_stream(bw)), bw)
    with pytest.raises(ValueError):
        I.unpack(b"short")


def test_pack_rejects_wrong_shape():
    with pytest.raises(ValueError):
        I.pack(np.zeros((10, 10), dtype=np.uint8))


def test_binarize_and_chunk():
    gray = np.array([[0, 127, 128, 255]], dtype=np.uint8)
    assert I.binarize(gray).tolist() == [[0, 0, 1, 1]]
    parts = I.chunk(bytes(10), 4)
    assert [len(p) for p in parts] == [4, 4, 2]
    with pytest.raises(ValueError):
        I.chunk(b"x", 0)
