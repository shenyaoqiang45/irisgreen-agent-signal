"""V0.2 verification on a real IrisGreen from a PC: command round trips and image transfer.

Uploads an asymmetric test image through the file-transfer service, plays it,
photographs the wall with a camera, then repeats the upload to check
reliability. Writes the evidence (frames and a JSON report) to --out.

This changes the device: it overwrites the group-1 slot file 1_1.bmp (the same slot the
IrisLoop tools use), plays it for a few seconds, then stops playback.

    python protocol/python/bleak/verify_transfer.py 20:6E:F1:81:71:62 --camera hik --repeat 10
    python protocol/python/bleak/verify_transfer.py ADDRESS --camera 0        # OpenCV camera 0
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
for _dir in ("sdk/ble-protocol-sdk", "sdk/capability-sdk", "protocol/python/bleak", "algorithms/calibration",
             "algorithms/coordinate-mapping", "algorithms/detection", "algorithms/tracking"):
    sys.path.insert(0, str(ROOT / _dir))

from bleak_transport import BleakTransport  # noqa: E402

from irisgreen_ble import IrisClient, image_pack  # noqa: E402
from irisgreen_capability import HikCamera, OpenCvCamera  # noqa: E402

W, H = image_pack.WIDTH, image_pack.HEIGHT
SLOT = 1


def test_image() -> np.ndarray:
    """Asymmetric 640x480 pattern: a flip or a mirror is visible at a glance."""
    img = np.zeros((H, W), np.uint8)
    cv2.rectangle(img, (8, 8), (W - 9, H - 9), 1, 3)
    cv2.rectangle(img, (24, 24), (104, 104), 1, -1)          # top-left: solid square
    cv2.rectangle(img, (W - 105, 24), (W - 25, 104), 1, 4)   # top-right: hollow square
    cv2.line(img, (W // 2 - 80, H - 30), (W // 2 + 80, H - 30), 1, 5)  # bottom centre: bar
    cv2.putText(img, "IRIS", (170, 250), cv2.FONT_HERSHEY_SIMPLEX, 3.4, 1, 9, cv2.LINE_AA)
    for x in range(40, W - 40, 20):                           # ticks along the bottom
        cv2.line(img, (x, H - 70), (x, H - 70 - (16 if (x // 20) % 5 == 0 else 8)), 1, 2)
    return img


def make_camera(spec: str, exposure_us: float | None):
    if spec == "hik":
        return HikCamera(exposure_us=exposure_us)
    if spec.startswith("hik:"):
        return HikCamera(spec[4:], exposure_us=exposure_us)
    return OpenCvCamera(int(spec))


def brightness_gain(frame: np.ndarray, baseline: np.ndarray) -> float:
    """Total brightness added over the baseline (works for mono and colour cameras)."""
    diff = frame.astype(np.int16).mean(axis=2) - baseline.astype(np.int16).mean(axis=2)
    return float(np.clip(diff, 0, None).sum())


async def main(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"address": args.address, "camera": args.camera, "steps": [], "uploads": []}
    failures: list[str] = []

    def check(ok: bool, what: str, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {what}" + (f"  [{detail}]" if detail else ""))
        report["steps"].append({"ok": ok, "what": what, "detail": detail})
        if not ok:
            failures.append(what)

    image = test_image()
    stream = image_pack.build_stream(image)
    check(len(stream) == image_pack.STREAM_BYTES, "stream size", f"{len(stream)} bytes")

    camera = make_camera(args.camera, args.exposure_us)
    try:
        async with IrisClient(BleakTransport(args.address), args.address) as client:
            info = await client.load_info()
            check(info.mtu >= 23, "connected", f"mtu {info.mtu}, {info.model} {info.serial}")

            # The camera is opened after BLE is up, on a worker thread (see OpenCvCamera).
            await camera.grab()
            if hasattr(camera, "describe"):
                print(f"INFO  camera: {camera.describe()}")

            stopped = await client.stop()
            check(stopped.ok, "stop playback (baseline)", stopped.error)
            await asyncio.sleep(1.0)
            baseline = await camera.grab()
            cv2.imwrite(str(out / "baseline.png"), baseline)

            t0 = time.perf_counter()
            await client.push_file(stream, f"{SLOT}_1.bmp")
            first_s = time.perf_counter() - t0
            check(True, "upload completed", f"{first_s:.2f}s for {len(stream)} bytes "
                  f"({len(stream) / first_s / 1024:.1f} KiB/s, mtu {info.mtu})")

            played = await client.play(SLOT, loop=True, total_100ms=args.show_s * 10, interval_100ms=10)
            check(played.ok, "play", played.error or played.raw.hex())
            await asyncio.sleep(1.5)
            shot = await camera.grab()
            cv2.imwrite(str(out / "projected.png"), shot)
            gain = brightness_gain(shot, baseline)
            check(gain > args.min_gain, "projection visible to the camera", f"brightness gain {gain:.0f}")
            report["brightness_gain"] = gain

            await client.stop()
            await asyncio.sleep(0.5)

            ok_count = 0
            times: list[float] = []
            for i in range(args.repeat):
                t = time.perf_counter()
                try:
                    await client.push_file(stream, f"{SLOT}_1.bmp")
                    good = (await client.get_picture_count()) is not None
                    detail = None
                except Exception as exc:
                    good, detail = False, f"{type(exc).__name__}: {exc}"
                dt = time.perf_counter() - t
                times.append(dt)
                ok_count += good
                report["uploads"].append({"i": i, "ok": good, "s": round(dt, 3), "error": detail})
                print(f"      upload {i + 1}/{args.repeat}: {'ok' if good else 'FAILED'} {dt:.2f}s")
                if not good:
                    break
            check(ok_count == args.repeat, f"{args.repeat} consecutive uploads",
                  f"{ok_count} ok, mean {np.mean(times):.2f}s" if times else "")

            played = await client.play(SLOT, loop=True, total_100ms=args.show_s * 10, interval_100ms=10)
            await asyncio.sleep(1.5)
            final = await camera.grab()
            cv2.imwrite(str(out / "after_repeat.png"), final)
            check(played.ok and brightness_gain(final, baseline) > args.min_gain,
                  "projection still visible after the repeat run")
            await client.stop()
            check((await client.get_brightness()) is not None, "device responsive at the end")
    finally:
        await camera.close()
        (out / "report.json").write_text(json.dumps(report, indent=2))

    print(f"\n{len(failures)} failure(s)" + (": " + "; ".join(failures) if failures else ""))
    print(f"evidence in {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("address")
    parser.add_argument("--camera", default="hik", help="'hik', 'hik:SERIAL' or an OpenCV index")
    parser.add_argument("--exposure-us", type=float, default=None, help="manual exposure for the Hik camera")
    parser.add_argument("--repeat", type=int, default=10, help="consecutive uploads for the reliability check")
    parser.add_argument("--show-s", type=int, default=6, help="seconds each projection stays up")
    parser.add_argument("--min-gain", type=float, default=50_000, help="brightness gain that counts as visible")
    parser.add_argument("--out", default=str(ROOT / "irisgreen_data" / "verify_pc"))
    sys.exit(asyncio.run(main(parser.parse_args())))
