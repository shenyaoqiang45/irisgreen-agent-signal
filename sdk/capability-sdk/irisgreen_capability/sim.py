"""A simulated IrisGreen, for development and tests without hardware.

`SimWorld` records what is projected. `SimTransport` behaves like the device
over BLE: it answers commands and accepts file uploads.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from irisgreen_ble import gatt_profile as G
from irisgreen_ble import image_pack
from irisgreen_ble import protocol as P
from irisgreen_ble.transport import NotifyCallback, Transport


class SimWorld:
    def __init__(self):
        self.mask = np.zeros((image_pack.HEIGHT, image_pack.WIDTH), np.uint8)
        self.playing = False
        self.uploads: list[tuple[str, int]] = []


class SimTransport(Transport):
    """Acts like an IrisGreen over BLE: answers commands, accepts file uploads."""

    def __init__(self, world: SimWorld, mtu: int = 512):
        self.world = world
        self._mtu = mtu
        self.connected = False
        self.commands: list[bytes] = []
        self._callbacks: dict[str, NotifyCallback] = {}
        self._upload: bytearray | None = None
        self._upload_name = ""
        self._upload_size = 0
        self.reads = {
            G.CHAR_MODEL_NUMBER: b"IrisGreen",
            G.CHAR_SERIAL_NUMBER: b"SIM0001",
            G.CHAR_FIRMWARE_REV: b"sim-1.0",
            G.CHAR_MANUFACTURER: b"AINSTEC",
            G.CHAR_BATTERY_LEVEL: (87).to_bytes(4, "little"),
        }

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    @property
    def mtu(self) -> int:
        return self._mtu

    async def read(self, uuid: str) -> bytes:
        if uuid not in self.reads:
            raise KeyError(uuid)
        return self.reads[uuid]

    async def start_notify(self, uuid: str, callback: NotifyCallback) -> None:
        self._callbacks[uuid] = callback

    async def stop_notify(self, uuid: str) -> None:
        self._callbacks.pop(uuid, None)

    async def write(self, uuid: str, data: bytes, response: bool) -> None:
        if not self.connected:
            raise RuntimeError("sim transport is not connected")
        data = bytes(data)
        if uuid == G.CHAR_MAIN_CMD:
            self._on_command(data)
        elif uuid == G.CHAR_FILE_START:
            self._upload_size = int.from_bytes(data[:4], "big")
            self._upload_name = data[4:].rstrip(b"\x00").decode("utf-8")
            self._upload = bytearray()
        elif uuid == G.CHAR_FILE_DATA:
            if self._upload is None:
                raise RuntimeError("file data before file start")
            self._upload.extend(data)
        elif uuid == G.CHAR_FILE_END:
            if self._upload is None or len(self._upload) != self._upload_size:
                raise RuntimeError(
                    f"upload size mismatch: got {0 if self._upload is None else len(self._upload)}, "
                    f"expected {self._upload_size}"
                )
            self.world.mask = image_pack.unpack(bytes(self._upload))
            self.world.uploads.append((self._upload_name, len(self._upload)))
            self._upload = None

    def _on_command(self, frame: bytes) -> None:
        self.commands.append(frame)
        cmd = frame[0]
        is_read = len(frame) >= 2 and frame[1] == 0
        payload = frame[2:]
        if cmd == P.CMD_PLAY and len(payload) == 6:
            self.world.playing = True
        elif cmd == P.CMD_PLAY_STOP:
            self.world.playing = False
        elif cmd == P.CMD_DELETE_PIC:
            self.world.mask = np.zeros_like(self.world.mask)
            self.world.playing = False
        if is_read:
            body = {P.CMD_BRIGHTNESS: b"\x32", P.CMD_PIC_COUNT: b"\x01\x00"}.get(cmd, b"\x00")
        else:
            body = payload[:1] or b"\x01"
        reply = bytes([P.RESP_PREFIX, cmd, len(body)]) + body
        callback = self._callbacks.get(G.CHAR_MAIN_CMD)
        if callback is not None:
            callback(reply)


@dataclass
class SimRig:
    """Everything needed to run the stack without hardware."""

    world: SimWorld
    transport: SimTransport


def make_rig() -> SimRig:
    world = SimWorld()
    return SimRig(world, SimTransport(world))


def make_sim_runtime(
    rig: SimRig | None = None,
    *,
    data_dir: str = "irisgreen_data",
    fast: bool = True,
):
    """A Runtime wired to the simulator. `fast` removes the real-time pacing delays."""
    from .runtime import Runtime

    rig = rig or make_rig()

    async def factory(address: str | None):
        return rig.transport, address or "SIM"

    return Runtime(
        transport_factory=factory,
        data_dir=data_dir,
        settle_s=0.0 if fast else 0.3,
        clear_s=0.0 if fast else 0.5,
        transfer_delay_s=0.0 if fast else None,
    ), rig
