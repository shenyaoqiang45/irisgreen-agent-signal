# IrisGreen GATT Profile (V0.1)

The BLE contract between IrisGreen hardware and any client. It is platform-independent: PC, Android and iOS use the same UUIDs and limits.

- Machine-readable source: [protocol/gatt/specification/irisgreen-gatt.json](../protocol/gatt/specification/irisgreen-gatt.json)
- Python constants: [gatt_profile.py](../sdk/ble-protocol-sdk/irisgreen_ble/gatt_profile.py) (a test keeps both in sync)

## Advertising

| Item | Value |
|---|---|
| Local name prefix | `Iris-G` (e.g. `Iris-G-B6B7CA`) |
| Advertised service | `adb401c0-b1c6-11ed-afa1-0242ac120002` |

## Main service `adb401c0-b1c6-11ed-afa1-0242ac120002`

| Characteristic | UUID | Properties | Purpose |
|---|---|---|---|
| status_read | `adb40001-b1c6-11ed-afa1-0242ac120001` | read | Status word (observed `01000000`) |
| notify | `adb40002-b1c6-11ed-afa1-0242ac120002` | read, notify | Unsolicited 8-byte status frames; not command responses |
| command | `adb40003-b1c6-11ed-afa1-0242ac120003` | write, indicate | Commands. Write with response; the reply arrives as an indication on this same characteristic |
| data | `adb40004-b1c6-11ed-afa1-0242ac120004` | write without response | Bulk data stream |
| command2 | `adb40005-b1c6-11ed-afa1-0242ac120005` | write | Spare command channel |

## File-transfer service `adb40006-b1c6-11ed-afa1-0242ac120001`

Used for image upload. Map by UUID suffix; the order in the protocol spreadsheet (R13/R14) has start and data swapped.

| Characteristic | UUID | Properties | Purpose |
|---|---|---|---|
| file_start | `adb40006-b1c6-11ed-afa1-0242ac120003` | write | Start packet |
| file_data | `adb40006-b1c6-11ed-afa1-0242ac120002` | write without response | Data chunks |
| file_end | `adb40006-b1c6-11ed-afa1-0242ac120004` | write | End packet |

## Standard characteristics

| Characteristic | UUID | Notes |
|---|---|---|
| Device Name | `00002a00-0000-1000-8000-00805f9b34fb` | |
| Battery Level | `00002a19-0000-1000-8000-00805f9b34fb` | Non-standard: 4 bytes little-endian, units unconfirmed |
| Model Number | `00002a24-0000-1000-8000-00805f9b34fb` | |
| Serial Number | `00002a25-0000-1000-8000-00805f9b34fb` | |
| Firmware Revision | `00002a26-0000-1000-8000-00805f9b34fb` | |
| Manufacturer Name | `00002a29-0000-1000-8000-00805f9b34fb` | |

## Link limits

- Negotiated MTU: 512 (observed).
- ATT overhead: 3 bytes, so the maximum payload per write is 509 bytes.
- Clients must use the actual negotiated MTU; fall back to 23 (20-byte payload) when it is unknown.

## V0.1 acceptance

PC, Android and iOS can connect, discover these services, and read the device identity. The PC path is [protocol/python/bleak/connect_demo.py](../protocol/python/bleak/connect_demo.py); Android and iOS (Flutter) go under `protocol/flutter/ble/`.
