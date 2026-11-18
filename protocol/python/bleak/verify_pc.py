"""V0.1 verification on a real IrisGreen from a PC: discover, compare against the GATT spec, read identity.

Read-only: it never writes to the device. Prints a PASS/FAIL line per check and
exits non-zero if any check fails.

    python protocol/python/bleak/verify_pc.py ADDRESS
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk" / "ble-protocol-sdk"))
sys.path.insert(0, os.path.dirname(__file__))

from bleak import BleakClient, BleakScanner  # noqa: E402

from irisgreen_ble import gatt_profile as G  # noqa: E402

SPEC = json.loads((ROOT / "protocol" / "gatt" / "specification" / "irisgreen-gatt.json").read_text())
failures: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {what}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures.append(what)


def info(what: str, detail: str) -> None:
    print(f"INFO  {what}: {detail}")


def warn(what: str, detail: str = "") -> None:
    print(f"WARN  {what}" + (f"  [{detail}]" if detail else ""))


def required_properties(props: list[str]) -> set[str]:
    """Spec names -> Bleak property names."""
    mapping = {"write_without_response": "write-without-response"}
    return {mapping.get(p, p) for p in props}


async def main(address: str) -> None:
    # 1. advertising
    found = await BleakScanner.discover(timeout=10, return_adv=True)
    device = next((t for t in found.values() if t[0].address.upper() == address.upper()), None)
    check(device is not None, "device is advertising", address)
    if device is None:
        return
    dev, adv = device
    name = adv.local_name or dev.name
    check(G.is_iris_projector(name, adv.service_uuids), "advertisement matches name prefix / service UUID", f"{name}")
    check(any(str(u).lower() == G.ADV_SERVICE_UUID for u in adv.service_uuids),
          "main service UUID is advertised")
    info("rssi", f"{adv.rssi} dBm")

    # 2. connect
    async with BleakClient(address, timeout=60.0) as client:
        check(client.is_connected, "connected")
        try:
            info("mtu", str(client.mtu_size))
            check(client.mtu_size >= 23, "MTU negotiated", str(client.mtu_size))
        except Exception as exc:
            info("mtu", f"unavailable ({exc})")

        # 3. GATT layout vs spec
        chars = {c.uuid.lower(): c for s in client.services for c in s.characteristics}
        services = {s.uuid.lower() for s in client.services}
        info("services", ", ".join(sorted(services)))
        check(G.SVC_MAIN in services, "main service present")
        check(G.SVC_SECONDARY in services, "file-transfer service present")

        for group in ("main", "file_transfer", "standard"):
            for key, spec in SPEC["services"][group]["characteristics"].items():
                char = chars.get(spec["uuid"].lower())
                if char is None:
                    check(False, f"{group}.{key} present", spec["uuid"])
                    continue
                want = required_properties(spec["properties"])
                missing = want - set(char.properties)
                check(not missing, f"{group}.{key} properties", f"{sorted(char.properties)}"
                      + (f" missing {sorted(missing)}" if missing else ""))

        # 4. identity (reads only)
        async def text(uuid: str) -> str:
            try:
                return bytes(await client.read_gatt_char(uuid)).decode("ascii", errors="replace")
            except Exception as exc:
                return f"<error {exc}>"

        # Model and serial may be blank on a unit that was never provisioned; that is unit data, not a
        # protocol failure, so it only warns. Firmware and manufacturer must be readable.
        for label, uuid, required in [("model", G.CHAR_MODEL_NUMBER, False), ("serial", G.CHAR_SERIAL_NUMBER, False),
                                      ("firmware", G.CHAR_FIRMWARE_REV, True),
                                      ("manufacturer", G.CHAR_MANUFACTURER, True)]:
            value = await text(uuid)
            readable = not value.startswith("<error")
            if value and readable:
                check(True, f"read {label}", value)
            elif required or not readable:
                check(False, f"read {label}", value or "empty")
            else:
                warn(f"{label} is empty on this unit", uuid)

        try:
            battery = bytes(await client.read_gatt_char(G.CHAR_BATTERY_LEVEL))
            check(len(battery) in (1, 4), "battery characteristic length", f"{len(battery)} bytes: {battery.hex()}")
        except Exception as exc:
            check(False, "read battery", str(exc))

        try:
            status = bytes(await client.read_gatt_char(G.CHAR_MAIN_STATUS_READ))
            info("status_read", status.hex())
        except Exception as exc:
            info("status_read", f"unreadable ({exc})")

        # 5. unsolicited status frames on the notify characteristic
        frames: list[bytes] = []
        try:
            await client.start_notify(G.CHAR_MAIN_NOTIFY, lambda _s, d: frames.append(bytes(d)))
            await asyncio.sleep(4)
            await client.stop_notify(G.CHAR_MAIN_NOTIFY)
            info("status frames in 4s", f"{len(frames)}" + (f", first {frames[0].hex()}" if frames else ""))
        except Exception as exc:
            info("notify", f"could not subscribe ({exc})")

    check(True, "disconnected cleanly")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    asyncio.run(main(sys.argv[1]))
    print(f"\n{len(failures)} failure(s)" + (": " + "; ".join(failures) if failures else ""))
    sys.exit(1 if failures else 0)
