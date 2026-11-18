"""Shared setup for the examples: import paths and a simulated or real Runtime."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_PACKAGE_DIRS = [
    "sdk/ble-protocol-sdk",
    "sdk/capability-sdk",
    "protocol/python/bleak",
    "algorithms/calibration",
    "algorithms/coordinate-mapping",
    "algorithms/detection",
    "algorithms/tracking",
]

# Lets `python examples/<name>/main.py` run from a clone without installing anything.
for _dir in _PACKAGE_DIRS:
    path = str(ROOT / _dir)
    if path not in sys.path:
        sys.path.insert(0, path)

from irisgreen_capability import CapabilityRegistry, HikCamera, OpenCvCamera, Runtime  # noqa: E402
from irisgreen_capability.sim import make_rig, make_sim_runtime  # noqa: E402


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--simulate", action="store_true",
                        help="run against a simulated projector, camera and wall (no hardware)")
    parser.add_argument("--address", default=None,
                        help="BLE address of the IrisGreen (default: the only one in range)")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index (hardware mode)")
    parser.add_argument("--hik", nargs="?", const="", default=None, metavar="SERIAL",
                        help="use a Hikrobot camera through the MVS SDK (optionally by serial number)")
    parser.add_argument("--exposure-us", type=float, default=None,
                        help="manual exposure for the Hik camera, in microseconds")
    parser.add_argument("--data-dir", default=str(ROOT / "irisgreen_data"))
    return parser


def make_runtime(args: argparse.Namespace, *, with_camera: bool) -> tuple[CapabilityRegistry, object]:
    """Returns (registry, rig). `rig` is the simulator when --simulate, else None."""
    if args.simulate:
        runtime, rig = make_sim_runtime(make_rig(moving_object=True), data_dir=args.data_dir)
        return CapabilityRegistry(runtime), rig
    camera = None
    if with_camera:
        camera = (HikCamera(args.hik or None, exposure_us=args.exposure_us)
                  if args.hik is not None else OpenCvCamera(args.camera))
    return CapabilityRegistry(Runtime(camera=camera, data_dir=args.data_dir)), None


def connect_args(args: argparse.Namespace) -> dict:
    """Arguments for device.connect: only include the address when one was given."""
    return {"address": args.address} if args.address else {}


def check(result: dict, step: str) -> dict:
    """Print a step's outcome and stop on failure."""
    if not result.get("ok"):
        error = result.get("error", {})
        raise SystemExit(f"{step} failed: {error.get('code')}: {error.get('message')}")
    print(f"ok  {step}")
    return result
