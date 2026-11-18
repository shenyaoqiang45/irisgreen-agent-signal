"""Image projection: draw a picture, project it full-field, then fit it onto a wall region.

The region step needs a calibration (it uses the camera), so it asks the camera
to see the projection field first.

    python examples/image-projection/main.py --simulate
"""

import argparse
import asyncio
import base64
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import add_arguments, check, connect_args, make_runtime  # noqa: E402


def draw_picture() -> str:
    """A 1-bit-friendly picture: a thick ring and a cross, as a base64 PNG."""
    image = np.zeros((300, 400), np.uint8)
    cv2.circle(image, (200, 150), 110, 255, 14)
    cv2.line(image, (200, 60), (200, 240), 255, 10)
    cv2.line(image, (110, 150), (290, 150), 255, 10)
    ok, buf = cv2.imencode(".png", image)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")


async def main(args: argparse.Namespace) -> None:
    registry, rig = make_runtime(args, with_camera=True)
    picture = draw_picture()
    try:
        check(await registry.call("device.connect", connect_args(args)), "device.connect")

        full = check(await registry.call("project.image", {"image_base64": picture, "seconds": 30}),
                     "project.image (full field)")
        print(f"    {full['lit_pixels']} lit pixels")
        await asyncio.sleep(0 if args.simulate else 3.0)

        check(await registry.call("calibration.calibrate", {}), "calibration.calibrate")
        # Fit the picture inside this rectangle of the camera view.
        region = [420, 260, 720, 460]
        placed = check(
            await registry.call("project.image",
                                {"image_base64": picture, "region": region, "seconds": 30}),
            f"project.image (camera region {region})",
        )
        print(f"    projector quad {placed['projector_quad']}")
        await asyncio.sleep(0 if args.simulate else 3.0)
    finally:
        await registry.call("project.clear", {})
        await registry.call("device.disconnect", {})
        await registry.runtime.close()
    print("done: the light is off")


if __name__ == "__main__":
    asyncio.run(main(add_arguments(argparse.ArgumentParser(description=__doc__)).parse_args()))
