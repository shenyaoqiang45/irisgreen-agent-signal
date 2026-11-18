import json
from pathlib import Path

import pytest

from irisgreen_ble import protocol as P

VECTORS = json.loads(
    (Path(__file__).parents[1] / "cross-platform" / "protocol-vectors.json").read_text()
)

BUILDERS = {
    "read brightness": lambda: P.build_read(P.CMD_BRIGHTNESS),
    "set brightness 100": lambda: P.cmd_set_brightness(100),
    "read picture count": lambda: P.build_read(P.CMD_PIC_COUNT),
    "set keystone mode 2": lambda: P.cmd_set_keystone(2),
    "set keystone angle 10": lambda: P.cmd_set_keystone_angle(10),
    "set keystone angle -10": lambda: P.cmd_set_keystone_angle(-10),
    "set keystone angle -70": lambda: P.cmd_set_keystone_angle(-70),
    "set fov 1": lambda: P.cmd_set_fov(1),
    "mirror on": lambda: P.cmd_set_mirror(True),
    "flip upside down": lambda: P.cmd_set_flip(True),
    "play group 0x0B (spec example)": lambda: P.cmd_play(0x0B, loop=False, total_100ms=100, interval_100ms=2),
    "play stop": P.cmd_play_stop,
    "delete group 5": lambda: P.cmd_delete_group(5),
}


def test_every_vector_has_a_builder():
    assert {v["name"] for v in VECTORS["commands"]} == set(BUILDERS)


@pytest.mark.parametrize("vec", VECTORS["commands"], ids=lambda v: v["name"])
def test_command_frames(vec):
    assert BUILDERS[vec["name"]]().hex().upper() == vec["frame"].upper()


@pytest.mark.parametrize("vec", VECTORS["responses"], ids=lambda v: v["name"])
def test_response_parsing(vec):
    resp = P.parse_response(bytes.fromhex(vec["raw"]))
    assert resp.ok == vec["ok"]
    if vec["ok"]:
        assert resp.cmd == vec["cmd"]
        assert resp.data.hex().upper() == vec["data"].upper()


@pytest.mark.parametrize("vec", VECTORS["file_packets"], ids=lambda v: v["name"])
def test_file_packets(vec):
    packet = P.build_file_packet(vec["size"], vec["file_name"])
    assert packet.hex().upper() == vec["packet"].upper()


def test_response_accessors():
    resp = P.parse_response(bytes.fromhex("8005022C01"))
    assert resp.u16_le == 300


def test_validation():
    with pytest.raises(ValueError):
        P.cmd_set_brightness(101)
    with pytest.raises(ValueError):
        P.cmd_set_keystone_angle(71)
    with pytest.raises(ValueError):
        P.cmd_play(1, total_100ms=36001)
    with pytest.raises(ValueError):
        P.build_write(P.CMD_NOTICE, bytes(256))
