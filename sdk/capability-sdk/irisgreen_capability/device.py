"""IrisGreen device: connection, projection and playback on top of the BLE SDK."""

from __future__ import annotations

import asyncio

import numpy as np

from irisgreen_ble import IrisClient, Transport
from irisgreen_ble import image_pack
from irisgreen_ble import protocol as P

from .errors import DEVICE_ERROR, INVALID_ARGUMENT, NOT_CONNECTED, CapabilityError

# Group 1 (the boot animation) is the writable slot. Live projection
# overwrites its first frame rather than deleting the group each time, which
# would blank the beam between uploads.
SLOT_GROUP = 1
PLAY_UNIT_MS = 100
PLAY_CAP_UNITS = 36000


def _half_up(value: float, unit: int) -> int:
    return max(1, int((value + unit / 2) // unit))


def play_units(seconds: float, frame_ms: int = 1000) -> tuple[int, int]:
    """Convert seconds and frame time into the protocol's 100 ms units.

    Sub-unit times round up to one unit; anything over one hour is rejected.
    """
    if seconds <= 0:
        raise ValueError("play time must be positive")
    if frame_ms <= 0:
        raise ValueError("frame time must be positive")
    total = _half_up(seconds * 1000, PLAY_UNIT_MS)
    if total > PLAY_CAP_UNITS:
        raise ValueError("play time cap is 1 hour")
    interval = _half_up(frame_ms, PLAY_UNIT_MS)
    return total, interval


class IrisDevice:
    def __init__(
        self,
        transport: Transport,
        address: str = "",
        *,
        settle_s: float = 0.3,
        clear_s: float = 0.5,
        transfer_delay_s: float | None = None,
    ):
        self.client = IrisClient(transport, address)
        if transfer_delay_s is not None:
            self.client.start_delay_s = transfer_delay_s
            self.client.packet_delay_s = transfer_delay_s
        self.settle_s = settle_s
        self.clear_s = clear_s
        self.connected = False
        self.projecting = False
        self.last_projection: dict | None = None
        self._slot_ready = False
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        try:
            await self.client.connect()
            await self.client.load_info()
        except Exception as exc:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            raise CapabilityError(DEVICE_ERROR, f"cannot connect: {exc}") from exc
        self.connected = True
        self._slot_ready = False

    async def disconnect(self) -> None:
        """Drop the BLE link. Playback already started keeps running on the device."""
        try:
            await self.client.disconnect()
        finally:
            self.connected = False

    def _require(self) -> None:
        if not self.connected:
            raise CapabilityError(NOT_CONNECTED, "no device connected; call device.connect first")

    async def _ensure_link(self) -> None:
        """Reconnect if the BLE link dropped while idle (the device or the OS may close it)."""
        if self.client.transport.is_connected:
            return
        try:
            await self.client.connect()
        except Exception as exc:
            self.connected = False
            raise CapabilityError(
                DEVICE_ERROR, f"the Bluetooth link dropped and reconnecting failed: {exc}; call device.connect"
            ) from exc

    def status(self) -> dict:
        info = self.client.info
        return {
            "connected": self.connected,
            "address": info.address,
            "model": info.model,
            "serial": info.serial,
            "firmware": info.firmware,
            "manufacturer": info.manufacturer,
            "battery_raw": info.battery_u32,
            "mtu": info.mtu,
            "projecting": self.projecting,
            "last_projection": self.last_projection,
        }

    async def show_mask(self, mask: np.ndarray, seconds: float = 3600.0) -> None:
        """Upload a 640x480 binary mask and play it. Calls are serialized."""
        self._require()
        if mask.shape != (image_pack.HEIGHT, image_pack.WIDTH):
            raise CapabilityError(
                INVALID_ARGUMENT,
                f"mask must be {image_pack.HEIGHT}x{image_pack.WIDTH}, got {mask.shape}",
            )
        try:
            total, interval = play_units(seconds)
        except ValueError as exc:
            raise CapabilityError(INVALID_ARGUMENT, str(exc)) from exc

        async with self._lock:
            await self._ensure_link()
            if not self._slot_ready:
                deleted = await self.client.send_command(P.cmd_delete_group(SLOT_GROUP))
                if not deleted.ok:
                    raise CapabilityError(DEVICE_ERROR, deleted.error or "could not clear slot")
                await asyncio.sleep(self.clear_s)
                self._slot_ready = True
            await self.client.push_file(
                image_pack.build_stream(mask), f"{SLOT_GROUP}_1.bmp"
            )
            await self.client.stop()
            await asyncio.sleep(self.settle_s)
            played = await self.client.play(SLOT_GROUP, True, total, interval)
            if not played.ok:
                raise CapabilityError(DEVICE_ERROR, played.error or "play was rejected")
        self.projecting = True
        self.last_projection = {
            "lit_pixels": int(mask.sum()),
            "seconds": total * PLAY_UNIT_MS / 1000,
        }

    async def clear(self, seconds: float = 5.0) -> None:
        """Project black so no light is emitted."""
        await self.show_mask(np.zeros((image_pack.HEIGHT, image_pack.WIDTH), np.uint8), seconds)
        self.projecting = False
        self.last_projection = None
