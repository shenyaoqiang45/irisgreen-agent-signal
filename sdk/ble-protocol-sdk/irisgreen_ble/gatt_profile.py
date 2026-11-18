"""IrisGreen GATT profile (V0.1): the BLE contract the device exposes.

Platform-independent constants only; no BLE library is imported, so PC,
Android and iOS clients share the same definitions. The machine-readable
source of truth is protocol/gatt/specification/irisgreen-gatt.json.
"""

from __future__ import annotations

# ---------------- primary custom service (commands / image stream) ----------------

SVC_MAIN = "adb401c0-b1c6-11ed-afa1-0242ac120002"

CHAR_MAIN_STATUS_READ = "adb40001-b1c6-11ed-afa1-0242ac120001"
CHAR_MAIN_NOTIFY = "adb40002-b1c6-11ed-afa1-0242ac120002"  # unsolicited status frames
CHAR_MAIN_CMD = "adb40003-b1c6-11ed-afa1-0242ac120003"     # write + indicate
CHAR_MAIN_DATA = "adb40004-b1c6-11ed-afa1-0242ac120004"    # write-without-response
CHAR_MAIN_CMD2 = "adb40005-b1c6-11ed-afa1-0242ac120005"    # spare command channel

# ---------------- secondary custom service (file transfer) ----------------

# Map by UUID suffix, not by the order in the protocol spreadsheet
# (its R13/R14 start/data descriptions are swapped relative to the UUIDs).
SVC_SECONDARY = "adb40006-b1c6-11ed-afa1-0242ac120001"

CHAR_FILE_START = "adb40006-b1c6-11ed-afa1-0242ac120003"
CHAR_FILE_DATA = "adb40006-b1c6-11ed-afa1-0242ac120002"
CHAR_FILE_END = "adb40006-b1c6-11ed-afa1-0242ac120004"

# ---------------- standard services ----------------

CHAR_DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"
CHAR_BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
CHAR_MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"
CHAR_SERIAL_NUMBER = "00002a25-0000-1000-8000-00805f9b34fb"
CHAR_FIRMWARE_REV = "00002a26-0000-1000-8000-00805f9b34fb"
CHAR_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"

# ---------------- advertising ----------------

ADV_SERVICE_UUID = SVC_MAIN
NAME_PREFIX = "Iris-G"  # advertised local name looks like Iris-G-B6B7CA

# ---------------- link limits ----------------

NEGOTIATED_MTU = 512
ATT_OVERHEAD = 3
MAX_CHUNK = NEGOTIATED_MTU - ATT_OVERHEAD  # 509


def is_iris_projector(name: str | None, service_uuids: list[str] | None = None) -> bool:
    """Return True if an advertisement looks like an IrisGreen projector."""
    if name and NAME_PREFIX.lower() in name.lower():
        return True
    if service_uuids:
        return any(u.lower() == ADV_SERVICE_UUID for u in service_uuids)
    return False
