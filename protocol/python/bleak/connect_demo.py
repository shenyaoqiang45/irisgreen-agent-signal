"""Connect to an IrisGreen device, read its identity and brightness.

Usage (from the repository root):
    python protocol/python/bleak/connect_demo.py [ADDRESS]
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk", "ble-protocol-sdk"))
sys.path.insert(0, os.path.dirname(__file__))

from bleak_transport import BleakTransport, scan  # noqa: E402
from irisgreen_ble import IrisClient  # noqa: E402


async def main(address: str | None) -> None:
    if address is None:
        devices = await scan()
        if not devices:
            raise SystemExit("no IrisGreen device found")
        address, name = devices[0]
        print(f"found {name} @ {address}")

    async with IrisClient(BleakTransport(address), address) as client:
        info = await client.load_info()
        print(f"model={info.model} serial={info.serial} firmware={info.firmware} mtu={info.mtu}")
        print(f"brightness={await client.get_brightness()}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
