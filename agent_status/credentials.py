"""Reporter tokens kept in one user-level file, outside any repository."""

import json
import os
import re
import secrets
import tempfile
from pathlib import Path

PORT = 8171
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


def store_path():
    return Path(os.environ.get("IGASP_HOME") or Path.home() / ".irisgreen") / "credentials.json"


def load(path=None):
    """Return {"port", "agents"}; a missing file is an empty store."""
    path = Path(path or store_path())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    agents = data.get("agents", {}) if isinstance(data, dict) else None
    port = data.get("port", PORT) if isinstance(data, dict) else None
    if (not isinstance(agents, dict) or not isinstance(port, int) or
            not all(isinstance(token, str) for token in agents.values())):
        raise ValueError(f'{path}: expected {{"port": 8171, "agents": {{"name": "token"}}}}')
    return {"port": port, "agents": dict(agents)}


def save(data, path=None):
    path = Path(path or store_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as f:
        tmp = Path(f.name)
        json.dump(data, f, indent=2)
        f.write("\n")
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def issue(agent, path=None):
    """Return the agent's token, creating and storing one when it has none."""
    if not _ID.fullmatch(agent):
        raise ValueError(f"invalid agent identity: {agent!r}")
    data = load(path)
    if agent not in data["agents"]:
        data["agents"][agent] = secrets.token_urlsafe(32)
        save(data, path)
    return data["agents"][agent]


def resolve(agent=None):
    """(agent, token, port) for a reporter: the environment first, then the store."""
    agent = agent or os.environ.get("IGASP_AGENT")
    if not agent:
        raise LookupError("no reporting identity: pass --agent or set IGASP_AGENT")
    token = os.environ.get("IGASP_TOKEN") if os.environ.get("IGASP_AGENT", agent) == agent else None
    port = os.environ.get("IGASP_PORT")
    if not token:
        try:
            data = load()
        except ValueError as exc:
            raise LookupError(str(exc)) from exc
        token, port = data["agents"].get(agent), port or data["port"]
    if not token:
        raise LookupError(f"no receiver token for {agent!r}: run python -m agent_status.setup")
    return agent, token, int(port or PORT)
