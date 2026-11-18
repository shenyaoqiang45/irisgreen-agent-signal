"""IrisGreen BLE Protocol SDK client (V0.2): commands and image transfer over a Transport."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from . import gatt_profile as G
from . import protocol as P
from .transport import Transport

WRITE_TIMEOUT = 15.0
DEFAULT_ATT_MTU = 23
START_DELAY_S = 0.1
PACKET_DELAY_S = 0.03


@dataclass
class DeviceInfo:
    """Device identity read after connect."""

    address: str = ""
    name: str = ""
    model: str = ""
    serial: str = ""
    firmware: str = ""
    manufacturer: str = ""
    battery_raw: bytes = b""
    mtu: int = 0

    @property
    def battery_u32(self) -> int | None:
        """Raw battery value. Device returns 4 bytes (non-standard); units unconfirmed."""
        if len(self.battery_raw) >= 4:
            return int.from_bytes(self.battery_raw[:4], "little")
        if self.battery_raw:
            return self.battery_raw[0]
        return None


class IrisClient:
    def __init__(self, transport: Transport, address: str = ""):
        self.transport = transport
        self.info = DeviceInfo(address=address)
        # Pacing of file transfers; tests and simulators set these to zero.
        self.start_delay_s = START_DELAY_S
        self.packet_delay_s = PACKET_DELAY_S

    # ---------- connection ----------

    async def connect(self) -> None:
        await self.transport.connect()
        self.info.mtu = self.transport.mtu

    async def disconnect(self) -> None:
        await self.transport.disconnect()

    async def __aenter__(self) -> "IrisClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    # ---------- command channel ----------

    async def send_command(
        self,
        frame: bytes,
        wait_response: bool = True,
        timeout: float = WRITE_TIMEOUT,
    ) -> P.Response:
        """Write a command frame; the response arrives as an indication on the same characteristic."""
        if not wait_response:
            await self.transport.write(G.CHAR_MAIN_CMD, frame, response=True)
            return P.Response(ok=True, raw=frame)

        got: list[bytes] = []
        await self.transport.start_notify(G.CHAR_MAIN_CMD, got.append)
        try:
            await self.transport.write(G.CHAR_MAIN_CMD, frame, response=True)

            deadline = time.perf_counter() + timeout
            seen = 0
            while time.perf_counter() < deadline:
                while seen < len(got):
                    resp = P.parse_response(got[seen])
                    seen += 1
                    if resp.ok and resp.cmd == frame[0]:
                        return resp
                await asyncio.sleep(0.02)

            if got:
                return P.Response(
                    ok=False,
                    raw=got[-1],
                    error=f"no matching cmd=0x{frame[0]:02X}, received {len(got)} frame(s)",
                )
            return P.Response(ok=False, error="timeout, no response")
        finally:
            try:
                await self.transport.stop_notify(G.CHAR_MAIN_CMD)
            except Exception:
                pass

    # ---------- device info ----------

    async def _read_string(self, uuid: str) -> str:
        try:
            return (await self.transport.read(uuid)).decode("ascii", errors="replace")
        except Exception:
            return ""

    async def load_info(self) -> DeviceInfo:
        self.info.model = await self._read_string(G.CHAR_MODEL_NUMBER)
        self.info.name = self.info.model
        self.info.serial = await self._read_string(G.CHAR_SERIAL_NUMBER)
        self.info.firmware = await self._read_string(G.CHAR_FIRMWARE_REV)
        self.info.manufacturer = await self._read_string(G.CHAR_MANUFACTURER)
        try:
            self.info.battery_raw = bytes(await self.transport.read(G.CHAR_BATTERY_LEVEL))
        except Exception:
            self.info.battery_raw = b""
        return self.info

    # ---------- image transfer ----------

    async def push_file(self, stream: bytes, name: str) -> None:
        """Upload a file (e.g. a 38462-byte 1bpp stream) via the file-transfer service."""
        packet = P.build_file_packet(len(stream), name)
        await self.transport.write(G.CHAR_FILE_START, packet, response=True)
        await asyncio.sleep(self.start_delay_s)

        mtu = self.transport.mtu or DEFAULT_ATT_MTU
        size = max(1, mtu - G.ATT_OVERHEAD)
        for i in range(0, len(stream), size):
            await self.transport.write(G.CHAR_FILE_DATA, stream[i : i + size], response=False)
            await asyncio.sleep(self.packet_delay_s)
        await self.transport.write(G.CHAR_FILE_END, packet, response=True)

    # ---------- high-level commands ----------

    async def get_picture_count(self) -> int | None:
        resp = await self.send_command(P.build_read(P.CMD_PIC_COUNT))
        return resp.u16_le if resp.ok else None

    async def get_brightness(self) -> int | None:
        resp = await self.send_command(P.build_read(P.CMD_BRIGHTNESS))
        return resp.data[0] if resp.ok and resp.data else None

    async def set_brightness(self, percent: int) -> P.Response:
        return await self.send_command(P.cmd_set_brightness(percent))

    async def get_keystone_mode(self) -> int | None:
        resp = await self.send_command(P.build_read(P.CMD_KEYSTONE_MODE))
        return resp.data[0] if resp.ok and resp.data else None

    async def set_keystone_mode(self, mode: int) -> P.Response:
        return await self.send_command(P.cmd_set_keystone(mode))

    async def set_keystone_angle(self, angle: int) -> P.Response:
        return await self.send_command(P.cmd_set_keystone_angle(angle))

    async def set_fov(self, level: int) -> P.Response:
        return await self.send_command(P.cmd_set_fov(level))

    async def set_mirror(self, enable: bool) -> P.Response:
        return await self.send_command(P.cmd_set_mirror(enable))

    async def set_flip(self, upside_down: bool) -> P.Response:
        return await self.send_command(P.cmd_set_flip(upside_down))

    async def play(
        self,
        group_id: int,
        loop: bool = False,
        total_100ms: int = 100,
        interval_100ms: int = 2,
    ) -> P.Response:
        return await self.send_command(P.cmd_play(group_id, loop, total_100ms, interval_100ms))

    async def stop(self) -> P.Response:
        return await self.send_command(P.cmd_play_stop())
