# IrisGreen Protocol Specification (V0.2)

Source: Iris Green Bluetooth Protocol V1.9 (2026-03-24). Implemented by the [BLE Protocol SDK](../sdk/ble-protocol-sdk/) on top of the [GATT profile](gatt-profile.md).

## Command frames

Written to the `command` characteristic with response.

```text
type(1) | len(1) | data(len)      len = 0 means "read"
```

Response, delivered as an indication on the same characteristic:

```text
80 | type(1) | len(1) | data(len)
```

- Some spreadsheet examples show a `08` prefix; clients accept both `80` and `08`.
- 8-byte frames beginning `00 00 01` and ending `00` are unsolicited status frames. They are not responses and must be skipped while waiting for a reply.
- A reply matches a request when `type` equals the request's `type`.
- Multi-byte values are little-endian. SN and model strings are returned byte-reversed.

## Commands used by the SDK

| Type | Name | Write payload |
|---|---|---|
| `0x05` | Picture count | read, returns u16 |
| `0x11` | Brightness | 1 byte, 0-100 |
| `0x12` | Flip | read, or write 0 upright / 1 upside-down |
| `0x1C` | Keystone mode | read, or write 0 off, 1 left right-angle, 2 isosceles, 3 right right-angle |
| `0x1D` | Keystone angle | read, or write -70..70; negatives are sent as `70 + abs(angle)` |
| `0x1E` | Mirror | read, or write 0 / 1 (default 0). With 0, the projected image appears horizontally mirrored on the wall as seen by a camera facing it; 1 shows it as authored (verified on hardware) |
| `0x1F` | FOV | read, or write 0 = 10x5 (documented default), 1 = 30x10, 2 = 20x10 |
| `0xA0` | Play material group | `loop(1) total_100ms(u16) interval_100ms(u16) group_id(1)`; total capped at 36000 |
| `0xA1` | Stop playback | `01` |
| `0xA2` | Delete material group | group id |

The full list of defined command types and material group IDs is in [protocol.py](../sdk/ble-protocol-sdk/irisgreen_ble/protocol.py). Golden frames shared by all platforms: [protocol-vectors.json](../tests/cross-platform/protocol-vectors.json).

## Image transfer

Images are uploaded through the file-transfer service.

1. Pack the 640x480 binary image into a 38462-byte stream (below).
2. Write the **file packet** to `file_start` (with response), then wait 50 ms.
3. Write the stream to `file_data` in chunks of `MTU - 3` bytes (without response). On PC (Bleak) the writes are flow-controlled by the BLE stack, so a 5 ms gap is enough: an upload takes about 2.8 s at MTU 512 and a gap of 0 gives the same time. The earlier 100 ms / 30 ms pacing took about 4.1 s. Other platforms should confirm their own minimum.
4. Write the same file packet to `file_end` (with response).

File packet: `size(u32, big-endian) | name(UTF-8, NUL-padded to at least 16 bytes)`.

### 1bpp stream

| Part | Size | Content |
|---|---|---|
| BMP header | 62 bytes | 14 file header + 40 DIB header + 8 palette (the spreadsheet's "124 bytes" is wrong) |
| Pixel data | 38400 bytes | 640x480, 1 bit per pixel, 80 bytes per row |

Pixel data is the image rotated 180 degrees (mirrored horizontally, flipped vertically, because the device reads BMP rows bottom-up), flattened row-major, 8 pixels per byte, most significant bit first. A set bit is a lit pixel.

Binarization (threshold, Otsu, dithering, edge extraction) is not part of the protocol; it belongs to the capability SDK's `render` module.
