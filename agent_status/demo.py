"""Replay the seven-step acceptance scenario without inspecting any agent runtime."""

import argparse
import asyncio
import os
import tempfile
import time
from pathlib import Path

from PIL import Image

from visualizer.device.mcp_adapter import McpDeviceAdapter
from visualizer.renderer.card import CardRenderer
from .mcp import send
from .output import checked
from .presentation import AgentPresentation
from .protocol import envelope
from .receiver import Receiver


def scenario():
    yield "idle", "status", {"state": "idle"}
    yield "thinking", "status", {"state": "thinking", "mood": "curious"}
    yield "working", "status", {"state": "working", "mood": "focused"}
    yield "discovery", "expression", {"intent": "discovery", "title": "Found the renderer", "duration_ms": 1500}
    yield "approval", "expression", {"expression_id": "review", "intent": "approval_required",
                                    "title": "Review the proposed change", "duration_ms": 10000}
    yield None, "expression.ack", {"expression_id": "review"}
    yield "resumed", "status", {"state": "working", "activity": "Applying reviewed change"}
    yield "completed", "status", {"state": "completed", "mood": "neutral"}


async def run(args):
    receiver = Receiver()
    presentation = AgentPresentation(receiver)
    renderer = CardRenderer()
    agent = os.environ.get("IGASP_AGENT", "demo")
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as data:
        device = McpDeviceAdapter(simulate=True, data_dir=data) if args.simulate_device else None
        if device:
            checked("connect", await device.connect())
        try:
            for label, kind, payload in scenario():
                event = envelope("agent." + kind, agent, "demo", payload)
                if args.http:
                    checked("report", send(event, os.environ["IGASP_TOKEN"], int(os.environ.get("IGASP_PORT", 8171))))
                receiver.receive(event, agent)
                if label:
                    card = presentation.current()
                    frame = renderer.frame(card, time.time())
                    Image.fromarray(frame * 255).save(args.out / f"{label}.png")
                    print(label, card.lines if card else "-", "lit pixels:", frame.sum(), flush=True)
                    if device:
                        checked("project", await device.push_frame(frame, seconds=2))
                    await asyncio.sleep(1.6)
        finally:
            if device:
                try:
                    checked("clear", await device.clear())
                finally:
                    checked("disconnect", await device.disconnect())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("irisgreen_data/igasp"))
    parser.add_argument("--simulate-device", action="store_true")
    parser.add_argument("--http", action="store_true", help="also send each report to the running receiver")
    asyncio.run(run(parser.parse_args()))
