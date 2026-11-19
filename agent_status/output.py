"""Operator-enabled projection; consume latest keyframes, not a BLE backlog."""

import asyncio
import tempfile
import time
from threading import Thread

from visualizer.device.mcp_adapter import McpDeviceAdapter


def checked(action, result):
    if not result.get("ok"):
        raise RuntimeError(f"{action}: {result}")


async def project(server, address, simulate, seconds):
    with tempfile.TemporaryDirectory() as data:
        device = McpDeviceAdapter(address=address, simulate=simulate, data_dir=data)
        checked("connect", await device.connect())
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2})
        thread.start()
        try:
            end = time.monotonic() + seconds if seconds is not None else float("inf")
            previous = None
            renew = 0.0
            while time.monotonic() < end:
                if not thread.is_alive():
                    raise RuntimeError("receiver stopped")
                latest = server.latest
                if latest is not None:
                    card, frame = latest
                    if card is None:
                        if previous is not None:
                            checked("clear", await device.clear())
                        previous = None
                    elif card.until > time.time() and (card != previous or time.monotonic() >= renew):
                        hold = min(3600.0, end - time.monotonic(), card.until - time.time())
                        if hold >= 0.1:
                            checked("project", await device.push_frame(frame, seconds=hold))
                            previous, renew = card, time.monotonic() + max(1.0, hold - 30)
                await asyncio.sleep(.2)
        finally:
            try:
                checked("clear", await device.clear())
            finally:
                try:
                    checked("disconnect", await device.disconnect())
                finally:
                    server.shutdown()
                    thread.join()
