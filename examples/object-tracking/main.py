"""Object tracking: put the laser dot on a chosen object and keep it there.

The target comes from a vision-language model that looks at the camera frame
(the autonomous path), or from a fixed box you pass with --bbox.

    # no hardware, no API key: a simulated wall and a scripted "VLM"
    python examples/object-tracking/main.py --simulate

    # real device, real VLM (any OpenAI-compatible endpoint)
    set IRISGREEN_VLM_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
    set IRISGREEN_VLM_KEY=...
    set IRISGREEN_VLM_MODEL=qwen3-vl-plus
    python examples/object-tracking/main.py --intent "the red-bordered patch"

    # real device, no VLM: you pick the box in camera pixels
    python examples/object-tracking/main.py --bbox 420 300 90 70
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import add_arguments, check, connect_args, make_runtime  # noqa: E402

from irisgreen_capability import openai_compatible_grounder, project_on_target  # noqa: E402


def scripted_grounder(rig):
    """Stands in for a VLM in the simulator: answers with the true object box (0-1000 coords)."""

    async def grounder(jpeg: bytes, prompt: str) -> str:
        o = rig.world.objects[0]
        w, h = rig.world.camera_size
        box = [o.x / w * 1000, o.y / h * 1000, (o.x + o.width) / w * 1000, (o.y + o.height) / h * 1000]
        return json.dumps([{"label": "patch", "bbox_2d": [round(v, 1) for v in box]}])

    return grounder


async def main(args: argparse.Namespace) -> None:
    registry, rig = make_runtime(args, with_camera=True)
    try:
        check(await registry.call("device.connect", connect_args(args)), "device.connect")

        if args.bbox:
            check(await registry.call("calibration.calibrate", {}), "calibration.calibrate")
            check(await registry.call("tracking.start", {"bbox": args.bbox}), "tracking.start")
            result = check(
                await registry.call("tracking.follow", {"duration_s": args.seconds}), "tracking.follow"
            )
            print(f"    {result['frames']} frames, {result['aimed_frames']} aimed")
            return

        if rig is not None:
            grounder = scripted_grounder(rig)
        else:
            url, key = os.environ.get("IRISGREEN_VLM_URL"), os.environ.get("IRISGREEN_VLM_KEY")
            if not (url and key):
                raise SystemExit("set IRISGREEN_VLM_URL and IRISGREEN_VLM_KEY, or pass --bbox")
            grounder = openai_compatible_grounder(
                url, key, os.environ.get("IRISGREEN_VLM_MODEL", "qwen3-vl-plus")
            )

        outcome = await project_on_target(registry, args.intent, grounder, follow_s=args.seconds)
        if not outcome["ok"]:
            raise SystemExit(f"failed at {outcome['stage']}: {outcome['error']['message']}")
        target, follow = outcome["target"], outcome["follow"]
        print(f"ok  tracked '{target['label']}' at {[round(v) for v in target['bbox']]}")
        print(f"    {follow['frames']} frames, {follow['aimed_frames']} aimed, "
              f"last position {[round(v) for v in follow['last']['center']]}")
    finally:
        await registry.call("project.clear", {})
        await registry.call("device.disconnect", {})
        await registry.runtime.close()
    print("done: the light is off")


if __name__ == "__main__":
    parser = add_arguments(argparse.ArgumentParser(description=__doc__,
                                                   formatter_class=argparse.RawDescriptionHelpFormatter))
    parser.add_argument("--intent", default="the object to highlight", help="what the VLM should find")
    parser.add_argument("--bbox", type=float, nargs=4, metavar=("X", "Y", "W", "H"),
                        help="skip the VLM and track this box (camera pixels)")
    parser.add_argument("--seconds", type=float, default=10.0, help="how long to follow the object")
    asyncio.run(main(parser.parse_args()))
