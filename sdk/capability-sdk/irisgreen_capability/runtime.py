"""Shared state behind the capabilities: device, camera, calibration, tracker."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Awaitable, Callable

from irisgreen_ble import Transport
from irisgreen_mapping import Calibration
from irisgreen_tracking import SingleObjectTracker, TemplateMeasurer

from .camera import Camera
from .device import IrisDevice
from .errors import INVALID_ARGUMENT, NO_CALIBRATION, NO_CAMERA, NOT_CONNECTED, CapabilityError

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
        camera: Camera | None = None,
        transport_factory: TransportFactory = bleak_transport_factory,
        calibration: Calibration | None = None,
        data_dir: str | Path = "irisgreen_data",
        clock: Callable[[], float] = time.monotonic,
        settle_s: float = 0.3,
        clear_s: float = 0.5,
        transfer_delay_s: float | None = None,
    ):
        self.device = device
        self.camera = camera
        self.transport_factory = transport_factory
        self.calibration = calibration
        self.data_dir = Path(data_dir)
        self.clock = clock
        self.settle_s = settle_s
        self.clear_s = clear_s
        self.transfer_delay_s = transfer_delay_s

        # TM_CCOEFF_NORMED scores a true match near 1; scenery alone stays well below 0.45.
        self.tracker = SingleObjectTracker(TemplateMeasurer(), min_score=0.45)
        self.tracking_last_t: float | None = None
        self.tracking_prev_velocity: tuple[float, float] | None = None
        self.projection_latency_s = 0.0

    # ---------- required resources ----------

    def require_device(self) -> IrisDevice:
        if self.device is None or not self.device.connected:
            raise CapabilityError(NOT_CONNECTED, "no device connected; call device.connect first")
        return self.device

    def require_camera(self) -> Camera:
        if self.camera is None:
            raise CapabilityError(NO_CAMERA, "no camera is configured")
        return self.camera

    def require_calibration(self) -> Calibration:
        if self.calibration is None:
            raise CapabilityError(
                NO_CALIBRATION, "not calibrated; call calibration.calibrate or calibration.load"
            )
        return self.calibration

    # ---------- files ----------

    def safe_path(self, name: str) -> Path:
        """Resolve `name` inside data_dir; refuse anything that escapes it."""
        root = self.data_dir.resolve()
        path = (root / name).resolve()
        if root != path and root not in path.parents:
            raise CapabilityError(INVALID_ARGUMENT, f"path must stay inside the data directory: {name}")
        return path

    def reset_tracking(self) -> None:
        self.tracker.reset()
        self.tracking_last_t = None
        self.tracking_prev_velocity = None

    async def close(self) -> None:
        if self.device is not None and self.device.connected:
            await self.device.disconnect()
        if self.camera is not None:
            await self.camera.close()
