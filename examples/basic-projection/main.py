"""Basic projection: connect, draw a dot, move it, clear.

    python examples/basic-projection/main.py --simulate
    python examples/basic-projection/main.py --address F4:12:FA:B6:B7:CA
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import add_arguments, check, connect_args, make_runtime  # noqa: E402


async def main(args: argparse.Namespace) -> None:
    registry, _ = make_runtime(args)
    try:
        info = check(await registry.call("device.connect", connect_args(args)), "device.connect")
        print(f"    {info['model']} {info['serial']} fw {info['firmware']} mtu {info['mtu']}")

        # Projector coordinates: 640x480, origin top-left.
        for x, y in [(160, 120), (480, 120), (480, 360), (160, 360), (320, 240)]:
            check(await registry.call("project.point", {"x": x, "y": y, "seconds": 30}),
                  f"project.point({x}, {y})")
            await asyncio.sleep(0 if args.simulate else 1.0)
    finally:
        await registry.call("project.clear", {})
        await registry.call("device.disconnect", {})
        await registry.runtime.close()
    print("done: the light is off")


if __name__ == "__main__":
    asyncio.run(main(add_arguments(argparse.ArgumentParser(description=__doc__)).parse_args()))
