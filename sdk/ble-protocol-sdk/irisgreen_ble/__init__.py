"""IrisGreen BLE Protocol SDK.

Layers:
    gatt_profile  GATT contract (UUIDs, limits)         - V0.1
    protocol      command frames and response parsing   - V0.2
    image_pack    1bpp image payload packing            - V0.2
    transport     platform BLE abstraction              - V0.2
    client        IrisClient built on a Transport       - V0.2
"""

from . import gatt_profile, image_pack, protocol
from .client import DeviceInfo, IrisClient
from .protocol import Response
from .transport import Transport

__all__ = [
    "DeviceInfo",
    "IrisClient",
    "Response",
    "Transport",
    "gatt_profile",
    "image_pack",
    "protocol",
]
