"""Cwd-independent stdio entry point for Codex, Cursor and other MCP clients."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_status.mcp import main

if __name__ == "__main__":
    asyncio.run(main())
