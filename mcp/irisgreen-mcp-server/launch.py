"""Start the IrisGreen MCP server straight from a repository clone.

Puts the repository's package directories on sys.path, so an MCP client only
needs `python <this file> [options]` and no PYTHONPATH:

    .venv/Scripts/python.exe mcp/irisgreen-mcp-server/launch.py --address 20:6E:F1:81:71:62
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _dir in ("sdk/ble-protocol-sdk", "sdk/capability-sdk", "protocol/python/bleak", "mcp/irisgreen-mcp-server"):
    sys.path.insert(0, str(ROOT / _dir))

from irisgreen_mcp import main  # noqa: E402

if __name__ == "__main__":
    # Relative data dir would otherwise depend on the client's working directory.
    if "--data-dir" not in sys.argv:
        sys.argv += ["--data-dir", str(ROOT / "irisgreen_data")]
    raise SystemExit(main())
