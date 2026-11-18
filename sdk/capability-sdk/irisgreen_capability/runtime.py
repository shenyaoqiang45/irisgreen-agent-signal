"""Shared state behind the capabilities: the device and the data directory."""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from irisgreen_ble import Transport

from .device import IrisDevice
from .errors import INVALID_ARGUMENT, NOT_CONNECTED, CapabilityError

# Resolves an optional BLE address to (transport, address). Scans when address is None.
TransportFactory = Callable[[str | None], Awaitable[tuple[Transport, str]]]


async def bleak_transport_factory(address: str | None) -> tuple[Transport, str]:
    """Default factory: Python + Bleak (protocol/python/bleak/bleak_transport.py)."""
    try:
        from bleak_transport import BleakTransport, scan
    except ImportError as exc:
        raise CapabilityError(
            INVALID_ARGUMENT,
            "the Bleak transport is not importable; add protocol/python/bleak to PYTHONPATH "
            "and install bleak",
        ) from exc
    if not address:
        found = await scan()
        if not found:
            raise CapabilityError("device_error", "no IrisGreen is advertising")
        if len(found) > 1:
            listing = ", ".join(f"{name} {addr}" for addr, name in found)
            raise CapabilityError(
                INVALID_ARGUMENT, f"more than one IrisGreen is nearby; pass address ({listing})"
            )
        address = found[0][0]
    return BleakTransport(address), address


class Runtime:
    def __init__(
        self,
        *,
        device: IrisDevice | None = None,
        transport_factory: TransportFactory = bleak_transport_factory,
        data_dir: str | Path = "irisgreen_data",
        settle_s: float = 0.3,
        clear_s: float = 0.5,
        transfer_delay_s: float | None = None,
        mirror_full_field: bool = False,
        default_address: str | None = None,
    ):
        self.device = device
        self.transport_factory = transport_factory
        self.data_dir = Path(data_dir)
        self.settle_s = settle_s
        self.clear_s = clear_s
        self.transfer_delay_s = transfer_delay_s
        # Used by device.connect when the caller gives no address (several projectors may be in range).
        self.default_address = default_address
        # With the device's mirror setting at 0 the wall shows a full-field image horizontally
        # mirrored, so such images are mirrored first.
        self.mirror_full_field = mirror_full_field

    # ---------- required resources ----------

    def require_device(self) -> IrisDevice:
        if self.device is None or not self.device.connected:
            raise CapabilityError(NOT_CONNECTED, "no device connected; call device.connect first")
        return self.device

    # ---------- files ----------

    def safe_path(self, name: str) -> Path:
        """Resolve `name` inside data_dir; refuse anything that escapes it."""
        root = self.data_dir.resolve()
        path = (root / name).resolve()
        if root != path and root not in path.parents:
            raise CapabilityError(INVALID_ARGUMENT, f"path must stay inside the data directory: {name}")
        return path

    async def close(self) -> None:
        if self.device is not None and self.device.connected:
            await self.device.disconnect()
