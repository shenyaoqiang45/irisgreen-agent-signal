"""IrisGreen Capability SDK (V0.3).

Unified projection, camera and status capabilities for AI agents, built on the
BLE Protocol SDK and the reference algorithms.
"""

from .camera import Camera, OpenCvCamera, StaticCamera
from .capabilities import Capability, CapabilityRegistry, build_capabilities
from .device import IrisDevice, play_units
from .errors import CapabilityError
from .runtime import Runtime, bleak_transport_factory
from .tasks import Grounder, project_on_target
from .vlm import openai_compatible_grounder

__all__ = [
    "Camera",
    "Capability",
    "CapabilityError",
    "CapabilityRegistry",
    "Grounder",
    "IrisDevice",
    "OpenCvCamera",
    "Runtime",
    "StaticCamera",
    "bleak_transport_factory",
    "build_capabilities",
    "openai_compatible_grounder",
    "play_units",
    "project_on_target",
]
