"""A simulated IrisGreen + camera + wall, for development and tests without hardware.

`SimWorld` owns the ground truth (a projector->camera homography and moving
objects). `SimTransport` behaves like the device over BLE and records what is
projected; `SimCamera` renders what a camera would see, including the green
projected light.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from irisgreen_ble import gatt_profile as G
from irisgreen_ble import image_pack
from irisgreen_ble import protocol as P
from irisgreen_ble.transport import NotifyCallback, Transport

from .camera import Camera

CAMERA_SIZE = (1280, 720)  # width, height

# Ground-truth projector -> camera homography for the simulated rig.
TRUE_H = np.array(
    [[1.3, 0.06, 90.0],
     [-0.05, 1.3, 40.0],
     [5e-5, 2e-5, 1.0]],
    dtype=np.float64,
)


@dataclass
class SimObject:
    """A textured patch drifting across the wall, bouncing off its limits."""

    x: float
    y: float
    vx: float
    vy: float
    width: int = 90
    height: int = 70
    seed: int = 7
    bounds: tuple[float, float, float, float] = (200.0, 150.0, 1000.0, 560.0)

    def step(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        x0, y0, x1, y1 = self.bounds
        if self.x < x0 or self.x + self.width > x1:
            self.vx = -self.vx
            self.x = min(max(self.x, x0), x1 - self.width)
        if self.y < y0 or self.y + self.height > y1:
            self.vy = -self.vy
            self.y = min(max(self.y, y0), y1 - self.height)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def texture(self) -> np.ndarray:
        rng = np.random.default_rng(self.seed)
        blocks = rng.integers(0, 255, (self.height // 6 + 1, self.width // 6 + 1, 3), dtype=np.uint8)
        blocks[..., 1] //= 2  # keep it from looking like laser green
        tex = cv2.resize(blocks, (self.width, self.height), interpolation=cv2.INTER_NEAREST)
        cv2.rectangle(tex, (0, 0), (self.width - 1, self.height - 1), (20, 60, 230), 3)
        return tex


class SimWorld:
    def __init__(
        self,
        *,
        H: np.ndarray | None = None,
        camera_size: tuple[int, int] = CAMERA_SIZE,
        objects: list[SimObject] | None = None,
        seed: int = 3,
    ):
        self.H = TRUE_H.copy() if H is None else np.asarray(H, dtype=np.float64)
        self.camera_size = camera_size
        self.objects = objects or []
        self.mask = np.zeros((image_pack.HEIGHT, image_pack.WIDTH), np.uint8)
        self.playing = False
        # Objects hold still while paused (calibration assumes a static scene).
        self.paused = False
        # Optional extra rule: objects also hold still whenever this returns True.
        self.still_when: Callable[[], bool] | None = None
        self.t = 0.0
        self.uploads: list[tuple[str, int]] = []
        rng = np.random.default_rng(seed)
        w, h = camera_size
        coarse = rng.integers(40, 110, (h // 16 + 1, w // 16 + 1), dtype=np.uint8)
        wall = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_CUBIC)
        self._wall = cv2.merge([wall, wall, np.clip(wall.astype(np.int16) + 8, 0, 255).astype(np.uint8)])

    def step(self, dt: float) -> None:
        self.t += dt
        if self.paused or (self.still_when is not None and self.still_when()):
            return
        for obj in self.objects:
            obj.step(dt)

    def render(self) -> np.ndarray:
        frame = self._wall.copy()
        for obj in self.objects:
            tex = obj.texture()
            x, y = int(round(obj.x)), int(round(obj.y))
            h, w = tex.shape[:2]
            frame[y:y + h, x:x + w] = tex
        if self.playing and self.mask.any():
            light = cv2.warpPerspective(
                self.mask * 255, self.H, self.camera_size,
                flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0,
            )
            frame[light > 0] = (60, 255, 60)
        return frame

    def camera_to_projector(self, point) -> tuple[float, float]:
        """Ground truth: where on the projector a camera pixel lies."""
        a = np.asarray(point, dtype=np.float64).reshape(1, 1, 2)
        out = cv2.perspectiveTransform(a, np.linalg.inv(self.H)).reshape(2)
        return float(out[0]), float(out[1])

    def lit_camera_centroid(self) -> tuple[float, float] | None:
        """Ground truth: centroid of the projected light in camera pixels."""
        if not (self.playing and self.mask.any()):
            return None
        ys, xs = np.nonzero(self.mask)
        a = np.array([[[xs.mean(), ys.mean()]]], dtype=np.float64)
        out = cv2.perspectiveTransform(a, self.H).reshape(2)
        return float(out[0]), float(out[1])


class SimTransport(Transport):
    """Acts like an IrisGreen over BLE: answers commands, accepts file uploads."""

    def __init__(self, world: SimWorld, mtu: int = 512):
        self.world = world
        self._mtu = mtu
        self.connected = False
        self.commands: list[bytes] = []
        self._callbacks: dict[str, NotifyCallback] = {}
        self._upload: bytearray | None = None
        self._upload_name = ""
        self._upload_size = 0
        self.reads = {
            G.CHAR_MODEL_NUMBER: b"IrisGreen",
            G.CHAR_SERIAL_NUMBER: b"SIM0001",
            G.CHAR_FIRMWARE_REV: b"sim-1.0",
            G.CHAR_MANUFACTURER: b"AINSTEC",
            G.CHAR_BATTERY_LEVEL: (87).to_bytes(4, "little"),
        }

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    @property
    def mtu(self) -> int:
        return self._mtu

    async def read(self, uuid: str) -> bytes:
        if uuid not in self.reads:
            raise KeyError(uuid)
        return self.reads[uuid]

    async def start_notify(self, uuid: str, callback: NotifyCallback) -> None:
        self._callbacks[uuid] = callback

    async def stop_notify(self, uuid: str) -> None:
        self._callbacks.pop(uuid, None)

    async def write(self, uuid: str, data: bytes, response: bool) -> None:
        if not self.connected:
            raise RuntimeError("sim transport is not connected")
        data = bytes(data)
        if uuid == G.CHAR_MAIN_CMD:
            self._on_command(data)
        elif uuid == G.CHAR_FILE_START:
            self._upload_size = int.from_bytes(data[:4], "big")
            self._upload_name = data[4:].rstrip(b"\x00").decode("utf-8")
            self._upload = bytearray()
        elif uuid == G.CHAR_FILE_DATA:
            if self._upload is None:
                raise RuntimeError("file data before file start")
            self._upload.extend(data)
        elif uuid == G.CHAR_FILE_END:
            if self._upload is None or len(self._upload) != self._upload_size:
                raise RuntimeError(
                    f"upload size mismatch: got {0 if self._upload is None else len(self._upload)}, "
                    f"expected {self._upload_size}"
                )
            self.world.mask = image_pack.unpack(bytes(self._upload))
            self.world.uploads.append((self._upload_name, len(self._upload)))
            self._upload = None

    def _on_command(self, frame: bytes) -> None:
        self.commands.append(frame)
        cmd = frame[0]
        is_read = len(frame) >= 2 and frame[1] == 0
        payload = frame[2:]
        if cmd == P.CMD_PLAY and len(payload) == 6:
            self.world.playing = True
        elif cmd == P.CMD_PLAY_STOP:
            self.world.playing = False
        elif cmd == P.CMD_DELETE_PIC:
            self.world.mask = np.zeros_like(self.world.mask)
            self.world.playing = False
        if is_read:
            body = {P.CMD_BRIGHTNESS: b"\x32", P.CMD_PIC_COUNT: b"\x01\x00"}.get(cmd, b"\x00")
        else:
            body = payload[:1] or b"\x01"
        reply = bytes([P.RESP_PREFIX, cmd, len(body)]) + body
        callback = self._callbacks.get(G.CHAR_MAIN_CMD)
        if callback is not None:
            callback(reply)


class SimCamera(Camera):
    """Renders the simulated wall. Each grab advances the world by `dt_per_grab`."""

    def __init__(self, world: SimWorld, dt_per_grab: float = 0.1):
        self.world = world
        self.dt_per_grab = dt_per_grab

    async def grab(self) -> np.ndarray:
        self.world.step(self.dt_per_grab)
        return self.world.render()


@dataclass
class SimRig:
    """Everything needed to run the full stack without hardware."""

    world: SimWorld
    transport: SimTransport
    camera: SimCamera

    def clock(self) -> float:
        """Simulated time in seconds; advances only when the camera grabs a frame."""
        return self.world.t


def make_rig(*, moving_object: bool = True, dt_per_grab: float = 0.1) -> SimRig:
    objects = [SimObject(x=420.0, y=300.0, vx=60.0, vy=25.0)] if moving_object else []
    world = SimWorld(objects=objects)
    return SimRig(world, SimTransport(world), SimCamera(world, dt_per_grab))


def make_sim_runtime(
    rig: SimRig | None = None,
    *,
    data_dir: str = "irisgreen_data",
    fast: bool = True,
):
    """A Runtime wired to the simulator. `fast` removes the real-time pacing delays.

    Objects in the scene hold still until tracking starts, because calibration
    needs a static scene; once a track is active they move.
    """
    from .runtime import Runtime

    rig = rig or make_rig()

    async def factory(address: str | None):
        return rig.transport, address or "SIM"

    delay = 0.0 if fast else None
    runtime = Runtime(
        camera=rig.camera,
        transport_factory=factory,
        data_dir=data_dir,
        clock=rig.clock,
        settle_s=0.0 if fast else 0.3,
        clear_s=0.0 if fast else 0.5,
        transfer_delay_s=delay,
    )
    rig.world.still_when = lambda: not runtime.tracker.active
    return runtime, rig
