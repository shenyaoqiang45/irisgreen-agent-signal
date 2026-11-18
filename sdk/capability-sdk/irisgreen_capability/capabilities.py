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

from irisgreen_calibration import CalibrationError, calibrate
from irisgreen_detection import to_1bpp
from irisgreen_detection.binarize import MODES
from irisgreen_mapping import (
    PROJ_HEIGHT,
    PROJ_WIDTH,
    Calibration,
    camera_point_to_projector,
    in_projection_field,
    place_in_camera_rect,
)
from irisgreen_calibration import make_dot_image
from irisgreen_tracking import aim_camera_point

from . import errors as E
from .device import IrisDevice
from .errors import CapabilityError
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
        "Connect to an IrisGreen projector over Bluetooth. Omit address to use the only "
        "device in range. Must be called before any projection.",
        _object({"address": {"type": "string", "description": "BLE address or platform id"}}),
        _result({"model": {"type": "string"}, "serial": {"type": "string"}, "mtu": {"type": "integer"}}),
    )
    async def device_connect(args: dict) -> dict:
        if rt.device is not None and rt.device.connected:
            return {"ok": True, "already_connected": True, **rt.device.status()}
        transport, address = await rt.transport_factory(args.get("address"))
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
        rt.reset_tracking()
        if rt.device is not None and rt.device.connected:
            await rt.device.disconnect()
        return {"ok": True}

    @cap(
        "device.get_status",
        "Report connection, device identity, whether light is being projected, and whether "
        "a camera, calibration and tracker are ready.",
        _object({}),
        _result({
            "connected": {"type": "boolean"},
            "projecting": {"type": "boolean"},
            "camera": {"type": "boolean"},
            "calibrated": {"type": "boolean"},
            "tracking": {"type": "boolean"},
        }),
    )
    async def device_get_status(args: dict) -> dict:
        status = rt.device.status() if rt.device is not None else {"connected": False, "projecting": False}
        return {
            "ok": True,
            **status,
            "camera": rt.camera is not None,
            "calibrated": rt.calibration is not None,
            "tracking": rt.tracker.active,
        }

    # ---------------- projection ----------------

    @cap(
        "project.point",
        "Project a single laser dot. space 'projector' uses the 640x480 projector field; "
        "space 'camera' takes a camera pixel and maps it through the calibration.",
        _object({
            "x": NUMBER,
            "y": NUMBER,
            "space": {"enum": ["projector", "camera"], "default": "projector"},
            "radius": {"type": "integer", "minimum": 2, "maximum": 60, "default": 12},
            "seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600, "default": 3600},
        }, ("x", "y")),
        _result({"projector": POINT, "camera": {"anyOf": [POINT, {"type": "null"}]}}),
    )
    async def project_point(args: dict) -> dict:
        device = rt.require_device()
        x, y = float(args["x"]), float(args["y"])
        if args.get("space", "projector") == "camera":
            try:
                px, py = camera_point_to_projector(rt.require_calibration(), (x, y))
            except ValueError as exc:
                raise CapabilityError(E.OUT_OF_FIELD, str(exc)) from exc
        else:
            _check_projector_point(x, y)
            px, py = x, y
        await device.show_mask(
            make_dot_image(px, py, int(args.get("radius", 12))), float(args.get("seconds", 3600))
        )
        camera_xy = None
        if rt.calibration is not None:
            cx, cy = rt.calibration.proj_to_cam([px, py])[0]
            camera_xy = [float(cx), float(cy)]
        return {"ok": True, "projector": [px, py], "camera": camera_xy}

    @cap(
        "project.image",
        "Project an image as 1-bit light. Give image_path (a file inside the data directory) "
        "or image_base64. Without region the image fills the projector field; with region "
        "[x0,y0,x1,y1] in camera pixels it is fitted inside that area of the wall "
        "(requires calibration).",
        _object({
            "image_path": {"type": "string"},
            "image_base64": {"type": "string"},
            "mode": {"enum": list(MODES), "default": "threshold"},
            "region": {"type": "array", "items": NUMBER, "minItems": 4, "maxItems": 4},
            "seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600, "default": 3600},
        }),
        _result({"lit_pixels": {"type": "integer"}, "projector_quad": {"type": "array"}}),
    )
    async def project_image(args: dict) -> dict:
        device = rt.require_device()
        gray = _decode_image(rt, args)
        mode = args.get("mode", "threshold")
        region = args.get("region")
        quad = None
        try:
            if region is not None:
                placed, quad_arr = place_in_camera_rect(
                    to_1bpp(gray, mode), rt.require_calibration(), tuple(region)
                )
                mask, quad = placed, quad_arr.round(1).tolist()
            else:
                resized = cv2.resize(gray, (PROJ_WIDTH, PROJ_HEIGHT), interpolation=cv2.INTER_AREA)
                mask = to_1bpp(resized, mode)
        except ValueError as exc:
            raise CapabilityError(E.OUT_OF_FIELD if region is not None else E.INVALID_ARGUMENT, str(exc)) from exc
        await device.show_mask(mask, float(args.get("seconds", 3600)))
        return {"ok": True, "lit_pixels": int(mask.sum()), "projector_quad": quad}

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

    # ---------------- camera ----------------

    @cap(
        "camera.capture",
        "Capture a camera frame as a JPEG so you can see the wall and choose targets. "
        "With overlay_field (needs calibration) the projectable area is outlined in orange.",
        _object({
            "quality": {"type": "integer", "minimum": 10, "maximum": 100, "default": 80},
            "overlay_field": {"type": "boolean", "default": False},
        }),
        _result({
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "mime_type": {"const": "image/jpeg"},
            "image_base64": {"type": "string"},
        }),
    )
    async def camera_capture(args: dict) -> dict:
        frame = await rt.require_camera().grab()
        if args.get("overlay_field", False):
            corners = [[0, 0], [PROJ_WIDTH - 1, 0], [PROJ_WIDTH - 1, PROJ_HEIGHT - 1], [0, PROJ_HEIGHT - 1]]
            quad = rt.require_calibration().proj_to_cam(corners)
            frame = frame.copy()
            cv2.polylines(frame, [np.rint(quad).astype(np.int32)], True, (0, 140, 255), 2)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(args.get("quality", 80))])
        if not ok:
            raise CapabilityError(E.INTERNAL, "could not encode the frame")
        h, w = frame.shape[:2]
        return {
            "ok": True, "width": w, "height": h, "mime_type": "image/jpeg",
            "image_base64": base64.b64encode(buf.tobytes()).decode("ascii"),
        }

    # ---------------- calibration ----------------

    def mapping_payload(calib: Calibration) -> dict:
        return {"ok": True, "H": np.asarray(calib.H).tolist(), "stats": calib.stats or {}}

    @cap(
        "calibration.load",
        "Load a saved calibration (JSON file inside the data directory).",
        _object({"path": {"type": "string"}}, ("path",)),
        _result({"H": {"type": "array"}, "stats": {"type": "object"}}),
    )
    async def calibration_load(args: dict) -> dict:
        try:
            calib = Calibration.load(str(rt.safe_path(args["path"])))
        except CapabilityError:
            raise
        except (OSError, ValueError, KeyError) as exc:
            raise _invalid(f"cannot load calibration: {exc}") from exc
        rt.calibration = calib
        return mapping_payload(calib)

    @cap(
        "calibration.calibrate",
        "Calibrate the projector against the camera: projects a grid of dots, finds each in "
        "the camera, and solves the mapping. Needs a connected device and a camera. "
        "Keep the camera view of the projection unobstructed.",
        _object({
            "cols": {"type": "integer", "minimum": 2, "maximum": 8, "default": 4},
            "rows": {"type": "integer", "minimum": 2, "maximum": 8, "default": 3},
            "save_path": {"type": "string", "description": "optional JSON file in the data directory"},
        }),
        _result({"H": {"type": "array"}, "stats": {"type": "object"}, "saved": {"type": ["string", "null"]}}),
    )
    async def calibration_calibrate(args: dict) -> dict:
        device, camera = rt.require_device(), rt.require_camera()
        save_to = rt.safe_path(args["save_path"]) if args.get("save_path") else None
        try:
            result = await calibrate(
                lambda mask: device.show_mask(mask, 60.0),
                camera.grab,
                cols=int(args.get("cols", 4)),
                rows=int(args.get("rows", 3)),
                settle_s=rt.settle_s + 0.1,
            )
        except CalibrationError as exc:
            raise CapabilityError(E.CALIBRATION_FAILED, str(exc)) from exc
        finally:
            try:
                await device.clear()
            except CapabilityError:
                pass
        rt.calibration = result.calibration
        if save_to is not None:
            result.calibration.save(str(save_to))
        return {**mapping_payload(result.calibration), "saved": str(save_to) if save_to else None}

    @cap(
        "calibration.get_mapping",
        "Return the current projector->camera homography and its fit statistics.",
        _object({}),
        _result({"H": {"type": "array"}, "stats": {"type": "object"}}),
    )
    async def calibration_get_mapping(args: dict) -> dict:
        return mapping_payload(rt.require_calibration())

    @cap(
        "calibration.map_point",
        "Convert a point between camera pixels and projector pixels using the calibration.",
        _object({
            "x": NUMBER, "y": NUMBER,
            "source": {"enum": ["camera", "projector"], "default": "camera"},
        }, ("x", "y")),
        _result({"x": NUMBER, "y": NUMBER, "in_field": {"type": "boolean"}}),
    )
    async def calibration_map_point(args: dict) -> dict:
        calib = rt.require_calibration()
        point = [float(args["x"]), float(args["y"])]
        if args.get("source", "camera") == "camera":
            mapped = calib.cam_to_proj(point)[0]
            return {"ok": True, "x": float(mapped[0]), "y": float(mapped[1]),
                    "in_field": in_projection_field(mapped)}
        mapped = calib.proj_to_cam(point)[0]
        return {"ok": True, "x": float(mapped[0]), "y": float(mapped[1]), "in_field": True}

    # ---------------- tracking ----------------

    def track_payload(track) -> dict:
        return {
            "center": [float(track.center[0]), float(track.center[1])],
            "velocity": [float(track.velocity[0]), float(track.velocity[1])],
            "bbox": [float(v) for v in track.bbox],
            "score": float(track.score),
            "measured": bool(track.measured),
        }

    @cap(
        "tracking.start",
        "Start tracking one object. bbox is [x, y, width, height] in camera pixels of the "
        "current camera view (use camera.capture to find it).",
        _object({"bbox": {"type": "array", "items": NUMBER, "minItems": 4, "maxItems": 4}}, ("bbox",)),
        _result({"center": POINT, "bbox": {"type": "array"}}),
    )
    async def tracking_start(args: dict) -> dict:
        frame = await rt.require_camera().grab()
        try:
            track = rt.tracker.start(frame, tuple(float(v) for v in args["bbox"]))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc
        rt.tracking_last_t = rt.clock()
        rt.tracking_prev_velocity = None
        return {"ok": True, **track_payload(track)}

    async def update_once(aim: bool, radius: int) -> dict:
        if not rt.tracker.active or rt.tracking_last_t is None:
            raise CapabilityError(E.NOT_TRACKING, "no active track; call tracking.start first")
        frame = await rt.require_camera().grab()
        now = rt.clock()
        dt = now - rt.tracking_last_t
        rt.tracking_last_t = now
        track = rt.tracker.update(frame, dt)
        if track is None:
            rt.reset_tracking()
            raise CapabilityError(E.TRACKING_LOST, "the object was lost; select it again")

        aimed: dict | None = None
        if aim:
            target = aim_camera_point(
                track.center, track.velocity, lead_s=rt.projection_latency_s,
                measured=track.measured, previous_velocity=rt.tracking_prev_velocity,
            )
            rt.tracking_prev_velocity = track.velocity
            if target is not None:
                try:
                    px, py = camera_point_to_projector(rt.require_calibration(), target)
                except ValueError:
                    aimed = {"projected": False, "reason": E.OUT_OF_FIELD}
                else:
                    started = rt.clock()
                    await rt.require_device().show_mask(make_dot_image(px, py, radius))
                    spent = max(0.0, rt.clock() - started)
                    rt.projection_latency_s = (
                        spent if rt.projection_latency_s == 0.0 else 0.7 * rt.projection_latency_s + 0.3 * spent
                    )
                    aimed = {"projected": True, "camera": [float(target[0]), float(target[1])],
                             "projector": [px, py]}
            else:
                aimed = {"projected": False, "reason": "no measurement this frame"}
        return {"ok": True, **track_payload(track), "aimed": aimed}

    @cap(
        "tracking.update",
        "Process one new camera frame for the tracked object and, with aim, move the laser "
        "dot onto it (leading it by the measured upload latency). Call repeatedly.",
        _object({
            "aim": {"type": "boolean", "default": True},
            "radius": {"type": "integer", "minimum": 2, "maximum": 60, "default": 12},
        }),
        _result({"center": POINT, "velocity": POINT, "measured": {"type": "boolean"},
                 "aimed": {"type": ["object", "null"]}}),
    )
    async def tracking_update(args: dict) -> dict:
        return await update_once(bool(args.get("aim", True)), int(args.get("radius", 12)))

    @cap(
        "tracking.follow",
        "Keep the laser dot on the tracked object for duration_s seconds (or max_frames "
        "frames), updating once per frame. Returns a summary and the last position.",
        _object({
            "duration_s": {"type": "number", "exclusiveMinimum": 0, "maximum": 600, "default": 10},
            "max_frames": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 300},
            "radius": {"type": "integer", "minimum": 2, "maximum": 60, "default": 12},
        }),
        _result({"frames": {"type": "integer"}, "aimed_frames": {"type": "integer"},
                 "last": {"type": "object"}}),
    )
    async def tracking_follow(args: dict) -> dict:
        duration = float(args.get("duration_s", 10))
        max_frames = int(args.get("max_frames", 300))
        radius = int(args.get("radius", 12))
        started = rt.clock()
        frames = aimed_frames = 0
        last: dict = {}
        while frames < max_frames and rt.clock() - started < duration:
            try:
                last = await update_once(True, radius)
            except CapabilityError as exc:
                if exc.code == E.TRACKING_LOST:
                    return {**exc.to_dict(), "frames": frames, "aimed_frames": aimed_frames}
                raise
            frames += 1
            if last["aimed"] and last["aimed"].get("projected"):
                aimed_frames += 1
        return {"ok": True, "frames": frames, "aimed_frames": aimed_frames, "last": last}

    @cap(
        "tracking.stop",
        "Stop tracking. The light is left as it is; call project.clear to turn it off.",
        _object({}),
        _result(),
    )
    async def tracking_stop(args: dict) -> dict:
        rt.reset_tracking()
        return {"ok": True}

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
