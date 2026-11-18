"""The IrisGreen capability set: semantic operations an AI agent can call.

Each capability has a stable name, a JSON input schema, a JSON output schema
and an async handler. Handlers return a dict with ``ok: true``; failures are
returned as ``{"ok": false, "error": {"code", "message"}}`` (see errors.py).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import cv2
import jsonschema
import numpy as np

from . import errors as E
from .device import IrisDevice
from .errors import CapabilityError
from .render import MODES, PROJ_HEIGHT, PROJ_WIDTH, in_projection_field, make_dot_image, to_1bpp
from .runtime import Runtime

Handler = Callable[[dict], Awaitable[dict]]

NUMBER = {"type": "number"}
POINT = {"type": "array", "items": NUMBER, "minItems": 2, "maxItems": 2}


def _object(properties: dict, required: tuple[str, ...] = ()) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _result(properties: dict | None = None) -> dict:
    """Output schema: always carries ``ok``; extra keys are described when known."""
    props = {"ok": {"const": True}}
    props.update(properties or {})
    return {"type": "object", "properties": props, "required": ["ok"]}


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    handler: Handler


def _invalid(message: str) -> CapabilityError:
    return CapabilityError(E.INVALID_ARGUMENT, message)


def _decode_image(rt: Runtime, args: dict) -> np.ndarray:
    """Load a grayscale image from `image_path` (inside the data dir) or `image_base64`."""
    path, b64 = args.get("image_path"), args.get("image_base64")
    if (path is None) == (b64 is None):
        raise _invalid("provide exactly one of image_path or image_base64")
    try:
        raw = (
            rt.safe_path(path).read_bytes() if path is not None else base64.b64decode(b64, validate=True)
        )
    except CapabilityError:
        raise
    except Exception as exc:
        raise _invalid(f"cannot read image: {exc}") from exc
    gray = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise _invalid("image data is not a decodable PNG/JPEG/BMP/WebP")
    return gray


def _check_projector_point(x: float, y: float) -> None:
    if not in_projection_field([x, y]):
        raise CapabilityError(
            E.OUT_OF_FIELD,
            f"({x}, {y}) is outside the {PROJ_WIDTH}x{PROJ_HEIGHT} projector field",
        )


def build_capabilities(rt: Runtime) -> list[Capability]:
    caps: list[Capability] = []

    def cap(name: str, description: str, inputs: dict, outputs: dict):
        def register(fn: Handler) -> Handler:
            caps.append(Capability(name, description, inputs, outputs, fn))
            return fn
        return register

    # ---------------- device ----------------

    @cap(
        "device.connect",
        "Connect to an IrisGreen projector over Bluetooth. Omit address to use the configured "
        "default or the only device in range. Must be called before any projection.",
        _object({"address": {"type": "string", "description": "BLE address or platform id"}}),
        _result({"model": {"type": "string"}, "serial": {"type": "string"}, "mtu": {"type": "integer"}}),
    )
    async def device_connect(args: dict) -> dict:
        if rt.device is not None and rt.device.connected:
            return {"ok": True, "already_connected": True, **rt.device.status()}
        transport, address = await rt.transport_factory(args.get("address") or rt.default_address)
        device = IrisDevice(
            transport, address, settle_s=rt.settle_s, clear_s=rt.clear_s,
            transfer_delay_s=rt.transfer_delay_s,
        )
        await device.connect()
        rt.device = device
        return {"ok": True, **device.status()}

    @cap(
        "device.disconnect",
        "Disconnect from the projector. Playback already started keeps running; "
        "call project.clear first to turn the light off.",
        _object({}),
        _result(),
    )
    async def device_disconnect(args: dict) -> dict:
        if rt.device is not None and rt.device.connected:
            await rt.device.disconnect()
        return {"ok": True}

    @cap(
        "device.get_status",
        "Report connection, device identity and whether light is being projected.",
        _object({}),
        _result({
            "connected": {"type": "boolean"},
            "projecting": {"type": "boolean"},
        }),
    )
    async def device_get_status(args: dict) -> dict:
        status = rt.device.status() if rt.device is not None else {"connected": False, "projecting": False}
        return {"ok": True, **status}

    # ---------------- projection ----------------

    @cap(
        "project.point",
        f"Project a single laser dot at a position in the {PROJ_WIDTH}x{PROJ_HEIGHT} projector field.",
        _object({
            "x": NUMBER,
            "y": NUMBER,
            "radius": {"type": "integer", "minimum": 2, "maximum": 60, "default": 12},
            "seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600, "default": 3600},
        }, ("x", "y")),
        _result({"projector": POINT}),
    )
    async def project_point(args: dict) -> dict:
        device = rt.require_device()
        x, y = float(args["x"]), float(args["y"])
        _check_projector_point(x, y)
        await device.show_mask(
            make_dot_image(x, y, int(args.get("radius", 12))), float(args.get("seconds", 3600))
        )
        return {"ok": True, "projector": [x, y]}

    @cap(
        "project.image",
        "Project an image as 1-bit light, filling the projector field. Give image_path "
        "(a file inside the data directory) or image_base64.",
        _object({
            "image_path": {"type": "string"},
            "image_base64": {"type": "string"},
            "mode": {"enum": list(MODES), "default": "threshold"},
            "seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600, "default": 3600},
        }),
        _result({"lit_pixels": {"type": "integer"}}),
    )
    async def project_image(args: dict) -> dict:
        device = rt.require_device()
        gray = _decode_image(rt, args)
        resized = cv2.resize(gray, (PROJ_WIDTH, PROJ_HEIGHT), interpolation=cv2.INTER_AREA)
        try:
            mask = to_1bpp(resized, args.get("mode", "threshold"))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc
        if rt.mirror_full_field:
            mask = mask[:, ::-1].copy()
        await device.show_mask(mask, float(args.get("seconds", 3600)))
        return {"ok": True, "lit_pixels": int(mask.sum())}

    @cap(
        "project.clear",
        "Turn the light off by projecting black.",
        _object({}),
        _result(),
    )
    async def project_clear(args: dict) -> dict:
        await rt.require_device().clear()
        return {"ok": True}

    @cap(
        "project.status",
        "Report whether light is currently projected and what was last shown.",
        _object({}),
        _result({"projecting": {"type": "boolean"}, "last_projection": {"type": ["object", "null"]}}),
    )
    async def project_status(args: dict) -> dict:
        device = rt.require_device()
        return {"ok": True, "projecting": device.projecting, "last_projection": device.last_projection}

    return caps


class CapabilityRegistry:
    """Looks capabilities up by name and validates arguments against their schema."""

    def __init__(self, runtime: Runtime):
        self.runtime = runtime
        self._caps = {c.name: c for c in build_capabilities(runtime)}

    def __iter__(self):
        return iter(self._caps.values())

    def names(self) -> list[str]:
        return list(self._caps)

    def get(self, name: str) -> Capability:
        try:
            return self._caps[name]
        except KeyError:
            raise CapabilityError(E.INVALID_ARGUMENT, f"unknown capability: {name}") from None

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict:
        """Run a capability. Never raises: failures come back as an error result."""
        try:
            capability = self.get(name)
            args = arguments or {}
            try:
                jsonschema.validate(args, capability.input_schema)
            except jsonschema.ValidationError as exc:
                where = ".".join(str(p) for p in exc.absolute_path)
                raise _invalid(f"{where + ': ' if where else ''}{exc.message}") from exc
            return await capability.handler(args)
        except CapabilityError as exc:
            return exc.to_dict()
        except Exception as exc:  # a bug or an unexpected device failure
            return CapabilityError(E.INTERNAL, f"{type(exc).__name__}: {exc}").to_dict()
