"""Python + Bleak reference implementation of the IrisGreen BLE transport (PC)."""

from __future__ import annotations

from bleak import BleakClient, BleakScanner

from irisgreen_ble import gatt_profile as G
from irisgreen_ble.transport import NotifyCallback, Transport


async def scan(timeout: float = 8.0) -> list[tuple[str, str]]:
    """Return (address, name) for every IrisGreen device in range."""
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    return [
        (device.address, adv.local_name or device.name or "")
        for device, adv in found.values()
        if G.is_iris_projector(adv.local_name or device.name, adv.service_uuids)
    ]


class BleakTransport(Transport):
    def __init__(self, address: str, connect_timeout: float = 60.0):
        self.address = address
        self._client = BleakClient(address, timeout=connect_timeout)

    async def connect(self) -> None:
        await self._client.connect()

    async def disconnect(self) -> None:
        try:
            await self._client.disconnect()
        except Exception:
            pass

    @property
    def mtu(self) -> int:
        try:
            return self._client.mtu_size
        except Exception:
            return 0

    async def write(self, uuid: str, data: bytes, response: bool) -> None:
        await self._client.write_gatt_char(uuid, data, response=response)

    async def read(self, uuid: str) -> bytes:
        return bytes(await self._client.read_gatt_char(uuid))

    async def start_notify(self, uuid: str, callback: NotifyCallback) -> None:
        await self._client.start_notify(uuid, lambda _sender, data: callback(bytes(data)))

    async def stop_notify(self, uuid: str) -> None:
        await self._client.stop_notify(uuid)
