"""IrisGreen Bluetooth command protocol (V1.9, 2026-03-24).

Frame format (written to the command characteristic):
    type(1) + len(1) + data(n)          len == 0 means "read"
Response frame:
    80 + type(1) + len(1) + data(n)

The spreadsheet describes the response prefix as "80" while some examples
write "08"; the example byte stream (`80 11 01 64`) shows 0x80, and both are
accepted when parsing.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable

# ---------------- command types ----------------

CMD_SN = 0x01                # read:0  write:15
CMD_MODEL = 0x02             # read:0  write:9
CMD_DEVICE_NAME = 0x03       # read:0  write:<=20 bytes (UTF-8, CJK <= 6 chars)
CMD_RESOURCE_VER = 0x04      # read:0
CMD_PIC_COUNT = 0x05         # read:0  -> 2-byte picture count
CMD_FORMAT = 0x06            # write:10  "Green@2026"
CMD_SHUTDOWN = 0x07          # write:1
CMD_REBOOT = 0x08            # write:1

CMD_TIME = 0x10              # write:4  local timestamp (little-endian u32)
CMD_BRIGHTNESS = 0x11        # read:0  write:1   0~100
CMD_FLIP = 0x12              # read:0  write:1   0=upright 1=upside-down
CMD_CHEER_MODE = 0x13        # read:0  write:1
CMD_HOURLY_CHIME = 0x14      # read:0  write:1
CMD_MILEAGE_ANNOUNCE = 0x15  # read:0  write:1
CMD_MILEAGE_INTERVAL = 0x16  # read:0  write:1   unit 100m
CMD_DRINK_REMIND = 0x17      # read:0  write:1
CMD_DRINK_INTERVAL = 0x18    # read:0  write:1   unit minutes
CMD_LAYOUT = 0x19            # write:1   0=minimal 1=standard
CMD_SPEED_UNIT = 0x1A        # write:1   0=KMH 1=MPH
CMD_LOW_BATTERY = 0x1B       # write:1   percent

CMD_KEYSTONE_MODE = 0x1C     # write:1   0=off 1=left right-angle 2=isosceles 3=right right-angle
CMD_KEYSTONE_ANGLE = 0x1D    # write:1   -70~70; >70 encodes a negative
CMD_MIRROR = 0x1E            # write:1   0/1
CMD_FOV = 0x1F               # write:1   0=10*5 1=30*10 2=20*10

CMD_PLAY = 0xA0              # write:6  play a full-frame material group
CMD_PLAY_STOP = 0xA1         # write:1
CMD_DELETE_PIC = 0xA2        # write:1  delete a material group
CMD_MATERIAL_PARAM = 0xA3    # read:0  write:2
CMD_WEATHER_TIME = 0xA4      # write:7
CMD_BG_PLAY = 0xA5           # write:4  background material (timer / hourly chime)
CMD_NOTICE = 0xA6            # write:<=32
CMD_PHONE_ALERT = 0xA7       # write:<=32

RESP_PREFIX = 0x80

# ---------------- material group IDs ----------------

MATERIAL_GROUPS = {
    1: "boot",
    2: "charging",
    3: "disconnected",
    4: "connected",
    5: "low battery",
    0x0A: "grid",
    0x0B: "animation",
    0x0C: "handwriting",
    0x0D: "prompt",
    0x0E: "speed 30 km/h",
    0x0F: "mileage",
    0x10: "hydration",
    0x11: "speed 40 km/h",
    0x12: "light-wheel trail",
    0x13: "climb",
    0x14: "descent",
    0x15: "geofence",
    0x16: "parking",
    0x17: "wake",
    0x18: "phone alert",
    # background images; IDs start at 51
    0x33: "battery",
    0x34: "weather/calendar_1",
    0x35: "weather/calendar_2",
    0x36: "weather/calendar_3",
    0x37: "timer",
    0x38: "minimal_speed",
    0x39: "minimal_avg_speed",
    0x3A: "minimal_mileage",
    0x3B: "minimal_time",
    0x3C: "minimal_altitude",
    0x3D: "minimal_calories",
    0x3E: "standard_layout_1",
    0x3F: "standard_layout_2",
    0x40: "standard_layout_3",
    0x41: "nav_left",
    0x42: "nav_right",
    0x43: "nav_straight",
    0x44: "nav_u-turn",
    0x45: "hourly chime",
}

MAX_MATERIAL_TOTAL = 200


def group_name(gid: int) -> str:
    return MATERIAL_GROUPS.get(gid, f"unknown(0x{gid:02X})")


# ---------------- frame builders ----------------


def build_write(cmd: int, data: bytes | Iterable[int] = b"") -> bytes:
    """Build a write frame: type + len + data."""
    d = bytes(data)
    if len(d) > 255:
        raise ValueError(f"data too long: {len(d)} > 255")
    return bytes([cmd & 0xFF, len(d)]) + d


def build_read(cmd: int) -> bytes:
    """Build a read frame: type + 0x00 (len=0 means read)."""
    return bytes([cmd & 0xFF, 0x00])


@dataclass
class Response:
    ok: bool
    cmd: int = 0
    data: bytes = b""
    raw: bytes = b""
    error: str = ""

    @property
    def text_ascii(self) -> str:
        """SN/Model fields: reverse little-endian then decode ASCII (per protocol)."""
        return bytes(self.data)[::-1].decode("ascii", errors="replace")

    @property
    def u16_le(self) -> int | None:
        if len(self.data) >= 2:
            return struct.unpack("<H", self.data[:2])[0]
        return None

    @property
    def u32_le(self) -> int | None:
        if len(self.data) >= 4:
            return struct.unpack("<I", self.data[:4])[0]
        return None


def is_status_frame(raw: bytes | bytearray) -> bool:
    """True if this is a device-initiated status frame (notify characteristic).

    Observed on-device: fixed 8 bytes like 00 00 01 22 00 00 0f 00, with byte 4
    as an incrementing counter. Not a command response.
    """
    b = bytes(raw)
    if len(b) != 8:
        return False
    return b[0] == 0x00 and b[1] == 0x00 and b[2] == 0x01 and b[7] == 0x00


def parse_response(raw: bytes | bytearray) -> Response:
    """Parse a response frame.

    - status frame -> not a command response (ok=False)
    - 0x80/0x08 prefix -> parsed per the spec
    - anything else -> ok=False with the raw bytes for the caller to inspect
    """
    b = bytes(raw)
    if len(b) < 3:
        return Response(ok=False, raw=b, error=f"response too short: {b.hex()}")

    if is_status_frame(b):
        return Response(ok=False, raw=b, error="status frame (not a command response)")

    if b[0] in (0x80, 0x08):
        length = b[2]
        return Response(ok=True, cmd=b[1], data=b[3 : 3 + length], raw=b)

    return Response(ok=False, raw=b, error=f"unknown frame format, first byte=0x{b[0]:02X}")


# ---------------- common command shortcuts ----------------


def cmd_set_keystone(mode: int) -> bytes:
    """Keystone mode: 0=off 1=left right-angle 2=isosceles 3=right right-angle."""
    if mode not in (0, 1, 2, 3):
        raise ValueError("mode must be 0..3")
    return build_write(CMD_KEYSTONE_MODE, [mode])


def cmd_set_keystone_angle(angle: int) -> bytes:
    """Keystone angle -70~70. Negatives encode as 70 + abs(angle).

    Example: -10 deg -> 80; -70 deg -> 140
    """
    if not -70 <= angle <= 70:
        raise ValueError("angle must be in -70..70")
    return build_write(CMD_KEYSTONE_ANGLE, [angle if angle >= 0 else 70 + abs(angle)])


def cmd_set_fov(level: int) -> bytes:
    """FOV preset: 0=10*5 1=30*10 2=20*10."""
    if level not in (0, 1, 2):
        raise ValueError("level must be 0..2")
    return build_write(CMD_FOV, [level])


def cmd_set_brightness(percent: int) -> bytes:
    if not 0 <= percent <= 100:
        raise ValueError("brightness must be in 0..100")
    return build_write(CMD_BRIGHTNESS, [percent])


def cmd_set_mirror(enable: bool) -> bytes:
    return build_write(CMD_MIRROR, [1 if enable else 0])


def cmd_set_flip(upside_down: bool) -> bytes:
    return build_write(CMD_FLIP, [1 if upside_down else 0])


def cmd_play(
    group_id: int,
    loop: bool = False,
    total_100ms: int = 100,
    interval_100ms: int = 2,
) -> bytes:
    """Play a full-frame material group (0xA0, 6 bytes).

    Spec example: A0 06 00 64 00 02 00 0B
      loop(1), total(u16 le), interval(u16 le), group_id(1)
    """
    if not 0 <= group_id <= 0xFF:
        raise ValueError("group_id out of range")
    if total_100ms > 36000:
        raise ValueError("total play time cap is 1 hour (36000 * 100ms)")
    data = (
        bytes([1 if loop else 0])
        + struct.pack("<H", total_100ms)
        + struct.pack("<H", interval_100ms)
        + bytes([group_id])
    )
    return build_write(CMD_PLAY, data)


def cmd_play_stop() -> bytes:
    return build_write(CMD_PLAY_STOP, [1])


def cmd_delete_group(group_id: int) -> bytes:
    return build_write(CMD_DELETE_PIC, [group_id & 0xFF])


def cmd_set_time(timestamp: int) -> bytes:
    return build_write(CMD_TIME, struct.pack("<I", timestamp & 0xFFFFFFFF))


# ---------------- file transfer packets ----------------

FILE_NAME_FIELD_MIN_BYTES = 16


def build_file_packet(file_size: int, file_name: str) -> bytes:
    """Start/end packet of a file transfer: size(u32 big-endian) + name (NUL padded to >=16 bytes).

    The same packet is written to both the start and the end characteristic.
    """
    name = file_name.encode("utf-8")
    field = max(FILE_NAME_FIELD_MIN_BYTES, len(name))
    return file_size.to_bytes(4, "big") + name.ljust(field, b"\x00")
