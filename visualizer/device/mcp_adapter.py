"""MCP-client adapter: project Visualizer 1bpp frames via IrisGreen MCP tools.

Launches mcp/irisgreen-mcp-server/launch.py over stdio (same pattern as
protocol/python/bleak/verify_mcp_image.py). Does not call Capability SDK / GATT
directly. Music code never imports this module.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

from visualizer.renderer import FIELD_HEIGHT, FIELD_WIDTH


def _parse_tool_result(result: Any) -> dict:
    data = getattr(result, "structured_content", None)
    if isinstance(data, dict):
        return data
    content = getattr(result, "content", None) or []
    if content:
        text = getattr(content[0], "text", None)
        if text:
            return json.loads(text)
    return {"ok": False, "error": {"message": f"unparseable MCP result: {result!r}"}}


def _guess_repo_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    cwd = Path.cwd().resolve()
    if (cwd / "mcp" / "irisgreen-mcp-server" / "launch.py").is_file():
        return cwd
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "mcp" / "irisgreen-mcp-server" / "launch.py").is_file():
            return parent
    return cwd


class McpDeviceAdapter:
    """Push 640x480 1bpp frames through MCP project_image (not direct GATT)."""

    def __init__(
        self,
        *,
        simulate: bool = False,
        address: str | None = None,
        repo_root: str | Path | None = None,
        data_dir: str | Path | None = None,
        mode: str = "threshold",
    ) -> None:
        self.simulate = bool(simulate)
        self.address = address
        self.repo_root = _guess_repo_root(repo_root)
        self.data_dir = Path(data_dir) if data_dir else (self.repo_root / "irisgreen_data")
        self.mode = mode
        self.launch_py = self.repo_root / "mcp" / "irisgreen-mcp-server" / "launch.py"

        self._client = None
        self._cm = None
        self._connected = False
        self.push_count = 0
        self.fail_count = 0
        self.last_error: str = ""
        self.last_result: dict[str, Any] | None = None
        self._frame_i = 0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def simulate_flag(self) -> bool:
        return self.simulate

    def status(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "simulate": self.simulate,
            "transport": "mcp",
            "address": self.address,
            "push_count": self.push_count,
            "fail_count": self.fail_count,
            "last_error": self.last_error,
            "last_result": self.last_result,
            "launch_py": str(self.launch_py),
            "data_dir": str(self.data_dir),
        }

    def _server_params(self):
        from mcp import StdioServerParameters

        if not self.launch_py.is_file():
            raise FileNotFoundError(f"MCP launch.py not found: {self.launch_py}")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        args = [str(self.launch_py), "--data-dir", str(self.data_dir.resolve())]
        if self.simulate:
            args.append("--simulate")
        return StdioServerParameters(command=sys.executable, args=args, env=None)

    async def connect(self) -> dict[str, Any]:
        from mcp import Client

        if self._connected and self._client is not None:
            out = {"ok": True, "already_connected": True, **self.status()}
            self.last_result = out
            return out
        try:
            params = self._server_params()
            self._cm = Client(params)
            self._client = await self._cm.__aenter__()
            tools = {t.name for t in (await self._client.list_tools()).tools}
            needed = {"device_connect", "project_image", "project_clear", "device_disconnect"}
            missing = needed - tools
            if missing:
                raise RuntimeError(f"MCP missing tools: {sorted(missing)}")
            args: dict[str, Any] = {}
            if self.address:
                args["address"] = self.address
            result = await self._client.call_tool("device_connect", args)
            data = _parse_tool_result(result)
            if getattr(result, "is_error", False):
                data = {"ok": False, "error": {"message": str(data)}}
            self.last_result = data
            if data.get("ok"):
                self._connected = True
                self.last_error = ""
            else:
                self._connected = False
                self.last_error = str((data.get("error") or {}).get("message") or data)
                await self._close_client()
            return data
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            self.last_error = repr(exc)
            self.last_result = {"ok": False, "error": {"message": repr(exc)}}
            await self._close_client()
            return self.last_result

    def _write_mask_png(self, mask: np.ndarray) -> str:
        arr = np.asarray(mask)
        if arr.shape != (FIELD_HEIGHT, FIELD_WIDTH):
            raise ValueError(f"mask must be {(FIELD_HEIGHT, FIELD_WIDTH)}, got {arr.shape}")
        pixels = (arr.astype(np.uint8) > 0).astype(np.uint8) * 255
        self._frame_i += 1
        name = f"viz_mcp_{self._frame_i:04d}.png"
        path = self.data_dir / name
        Image.fromarray(pixels, mode="L").save(path)
        return name

    async def push_frame(self, mask: np.ndarray, seconds: float = 3600.0) -> dict[str, Any]:
        if not self._connected or self._client is None:
            out = {"ok": False, "error": {"message": "not connected; call connect first"}}
            self.last_result = out
            self.fail_count += 1
            return out
        try:
            name = self._write_mask_png(mask)
            result = await self._client.call_tool(
                "project_image",
                {"image_path": name, "mode": self.mode, "seconds": float(seconds)},
            )
            data = _parse_tool_result(result)
            if getattr(result, "is_error", False) and data.get("ok") is not False:
                data = {"ok": False, "error": {"message": str(data)}}
            self.last_result = data
            if data.get("ok"):
                self.push_count += 1
                self.last_error = ""
            else:
                self.fail_count += 1
                self.last_error = str((data.get("error") or {}).get("message") or data)
            return data
        except Exception as exc:  # noqa: BLE001
            self.fail_count += 1
            self.last_error = repr(exc)
            self.last_result = {"ok": False, "error": {"message": repr(exc)}}
            return self.last_result

    async def clear(self) -> dict[str, Any]:
        if self._client is None:
            return {"ok": False, "error": {"message": "no MCP client"}}
        try:
            result = await self._client.call_tool("project_clear", {})
            data = _parse_tool_result(result)
            self.last_result = data
            return data
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": {"message": repr(exc)}}

    async def disconnect(self) -> dict[str, Any]:
        data: dict[str, Any] = {"ok": True}
        if self._client is not None:
            try:
                result = await self._client.call_tool("device_disconnect", {})
                data = _parse_tool_result(result)
            except Exception as exc:  # noqa: BLE001
                data = {"ok": False, "error": {"message": repr(exc)}}
        await self._close_client()
        self._connected = False
        self.last_result = data
        return data

    async def _close_client(self) -> None:
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._cm = None
        self._client = None
