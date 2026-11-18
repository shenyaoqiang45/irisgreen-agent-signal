# BLE Protocol SDK

Python implementation of the IrisGreen BLE protocol (roadmap V0.2). It has no BLE library dependency; each platform supplies a `Transport`.

| Module | Role |
|---|---|
| `gatt_profile` | GATT UUIDs and link limits (V0.1) |
| `protocol` | Command frames, response parsing, file packets |
| `image_pack` | 640x480 1bpp payload packing |
| `transport` | `Transport` interface that platforms implement |
| `client` | `IrisClient`: commands, device info, image upload |

```python
from irisgreen_ble import IrisClient, image_pack

async with IrisClient(my_transport) as client:
    await client.set_brightness(80)
    await client.push_file(image_pack.build_stream(bw), "1_1.bmp")
    await client.play(group_id=1)
```

The Python + Bleak transport is in [protocol/python/bleak](../../protocol/python/bleak). Tests live in [tests/protocol](../../tests/protocol); run `python -m pytest` from the repository root.
