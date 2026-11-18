"""IrisGreen Capability SDK (V0.3).

Device and projection capabilities for AI agents, built on the BLE Protocol SDK.
"""

from .capabilities import Capability, CapabilityRegistry, build_capabilities
from .device import IrisDevice, play_units
from .errors import CapabilityError
from .runtime import Runtime, bleak_transport_factory

__all__ = [
    "Capability",
    "CapabilityError",
    "CapabilityRegistry",
    "IrisDevice",
    "Runtime",
    "bleak_transport_factory",
    "build_capabilities",
    "play_units",
]
