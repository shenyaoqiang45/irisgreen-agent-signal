"""Smallest end-to-end check: an MCP client (standing in for the PC agent) makes the
real IrisGreen project an image. No camera and no calibration are involved.

    python protocol/python/bleak/verify_mcp_image.py --address 20:6E:F1:81:71:62
    python protocol/python/bleak/verify_mcp_image.py --simulate # no hardware
    python protocol/python/bleak/verify_mcp_image.py --image my.png --seconds 20

Tool calls: device_connect, project_image, project_status, (hold), project_clear,
device_disconnect. The light is always cleared at the end, even after an error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = [
    "sdk/ble-protocol-sdk", "sdk/capability-sdk", "protocol/python/bleak", "mcp/irisgreen-mcp-server",
]


def make_test_image(path: Path) -> None:
    """640x480, asymmetric on purpose: an arrow and the text 'IRIS' show any mirroring."""
    img = np.zeros((480, 640), np.uint8)
    cv2.rectangle(img, (4, 4), (635, 475), 255, 4)
    cv2.putText(img, "IRIS", (60, 200), cv2.FONT_HERSHEY_SIMPLEX, 4, 255, 10)
    cv2.arrowedLine(img, (60, 400), (580, 400), 255, 10, tipLength=0.15)
    cv2.circle(img, (110, 300), 30, 255, -1)  # top-left marker
    cv2.imwrite(str(path), img)


def parse(result) -> dict:
    return result.structured_content or json.loads(result.content[0].text)


async def run(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    if args.image:
        name = Path(args.image).name
        target = data_dir / name
        if Path(args.image).resolve() != target:
            target.write_bytes(Path(args.image).read_bytes())
    else:
        name = "mcp_test_image.png"
        make_test_image(data_dir / name)

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(str(ROOT / p) for p in PACKAGES)
    server_args = ["-m", "irisgreen_mcp", "--data-dir", str(data_dir)]
    if args.simulate:
        server_args.append("--simulate")
    params = StdioServerParameters(command=sys.executable, args=server_args, env=env)

    ok = True

    def step(label: str, result) -> dict:
        nonlocal ok
        data = parse(result)
        good = not result.is_error and data.get("ok", False)
        ok = ok and good
        print(f"[{'ok' if good else 'FAIL'}] {label}: {json.dumps(data, ensure_ascii=False)}")
        return data

    async with Client(params) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        print(f"tools: {len(tools)}")
        missing = {"device_connect", "project_image", "project_clear"} - tools
        if missing:
            print(f"[FAIL] missing tools: {sorted(missing)}")
            return 1
        try:
            step("device_connect", await client.call_tool(
                "device_connect", {"address": args.address} if args.address else {}))
            if ok:
                step("project_image", await client.call_tool("project_image", {
                    "image_path": name, "mode": args.mode, "seconds": args.seconds + 30,
                }))
                step("project_status", await client.call_tool("project_status", {}))
                if ok:
                    print(f"projecting for {args.seconds:g} s: look at the wall")
                    await asyncio.sleep(args.seconds)
        finally:
            step("project_clear", await client.call_tool("project_clear", {}))
            step("device_disconnect", await client.call_tool("device_disconnect", {}))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--address", help="BLE address (needed when several devices are in range)")
    parser.add_argument("--simulate", action="store_true", help="use the simulated device")
    parser.add_argument("--image", help="image to project (default: generated test image)")
    parser.add_argument("--mode", default="threshold", choices=["threshold", "otsu", "dither", "edges"])
    parser.add_argument("--seconds", type=float, default=10, help="how long to keep it on the wall")
    parser.add_argument("--data-dir", default=str(ROOT / "irisgreen_data"))
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
