"""Register the IrisGreen reporter with Cursor, Codex and VS Code Copilot.

python -m agent_status.setup            # all three
python -m agent_status.setup codex      # only the named clients

Each client launches mcp/irisgreen-agent-status/launch.py under its own identity.
Tokens stay in the credential store; no client configuration receives one.
"""

import argparse
import http.client
import json
import os
import re
import secrets
import sys
import tempfile
import tomllib
from pathlib import Path

from .credentials import load, save, store_path

NAME = "irisgreen-status"
LAUNCH = Path(__file__).resolve().parents[1] / "mcp" / "irisgreen-agent-status" / "launch.py"


def _home(variable, default):
    return Path(os.environ.get(variable) or Path.home() / default)


# label, user-level configuration file, client-specific fields of the server entry
CLIENTS = {
    "cursor": ("Cursor", lambda: Path.home() / ".cursor" / "mcp.json", {}),
    "codex": ("Codex", lambda: _home("CODEX_HOME", ".codex") / "config.toml", {"startup_timeout_sec": 30}),
    "copilot": ("VS Code Copilot", lambda: _home("COPILOT_HOME", ".copilot") / "mcp-config.json",
                {"type": "stdio", "tools": ["*"]}),
}


def plan(client, agents):
    """Decide how `client` gets the reporter, giving its identity a token in `agents`.

    Returns (status, identity, path, new_text or None, device) where `device` tells
    whether the client also starts the projector service.
    """
    path = CLIENTS[client][1]()
    text = path.read_bytes().decode("utf-8-sig") if path.exists() else ""
    toml = path.suffix == ".toml"
    data = tomllib.loads(text) if toml else json.loads(text if text.strip() else "{}")
    table = "mcp_servers" if toml else "mcpServers"
    servers = data.get(table, {}) if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        raise ValueError(f"{path}: {table} is not a table of servers")
    device = any(isinstance(server, dict) and
                 "irisgreen-mcp-server" in " ".join(map(str, server.get("args") or []))
                 for server in servers.values())
    current = servers.get(NAME) if isinstance(servers.get(NAME), dict) else {}
    inline = current.get("env") if isinstance(current.get("env"), dict) else {}
    token, identity = inline.get("IGASP_TOKEN"), inline.get("IGASP_AGENT", client)
    if isinstance(token, str) and len(token) >= 24 and agents.setdefault(identity, token) == token:
        return "kept", identity, path, None, device
    agents.setdefault(client, secrets.token_urlsafe(32))
    entry = {"command": sys.executable, "args": [str(LAUNCH), "--agent", client], **CLIENTS[client][2]}
    if current.get("command") == entry["command"] and current.get("args") == entry["args"]:
        return "unchanged", client, path, None, device
    newline = "\r\n" if "\r\n" in text else "\n"
    if toml:
        block = "\n".join([f"[mcp_servers.{NAME}]"] + [f"{key} = {json.dumps(value, ensure_ascii=False)}"
                                                       for key, value in entry.items()])
        if current:
            return "differs", client, path, block, device
        # Append only: every existing byte of the user's configuration stays as it is.
        new = (text.rstrip() + newline * 2 if text.strip() else "") + (block + "\n").replace("\n", newline)
        if tomllib.loads(new)["mcp_servers"][NAME]["args"] != entry["args"]:
            raise ValueError(f"{path}: could not add a server table")
    else:
        data[table] = {**servers, NAME: entry}
        indent = re.search(r'\n([ \t]+)"', text)
        new = json.dumps(data, indent=indent.group(1) if indent else 2, ensure_ascii=False) + "\n"
        new = new.replace("\n", newline)
    return ("updated" if current else "added"), client, path, new, device


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        f.write(text.encode("utf-8"))
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _receiver(token, port):
    """Whether a running receiver knows this token; reading an unknown session shows nothing."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("POST", "/api/v1/agent/snapshot/read", '{"session_id": "setup"}',
                           {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        return "rejects" if connection.getresponse().status in (401, 403) else "accepts"
    except (OSError, http.client.HTTPException):
        return "down"
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clients", nargs="*", metavar="CLIENT", help=f"default: {' '.join(CLIENTS)}")
    parser.add_argument("--port", type=int, help="receiver port to record (default: keep; 8171 at first)")
    args = parser.parse_args(argv)
    if set(args.clients) - set(CLIENTS):
        parser.error(f"choose from: {' '.join(CLIENTS)}")
    store = load()
    before = json.dumps(store, sort_keys=True)
    store["port"] = args.port or store["port"]
    plans, failed = {}, False
    for client in args.clients or CLIENTS:
        try:
            plans[client] = plan(client, store["agents"])
        except (OSError, ValueError) as exc:
            plans[client] = ("failed", client, CLIENTS[client][1](), None, False)
            failed = True
            print(f"{CLIENTS[client][0]}: {exc}", file=sys.stderr)
    if json.dumps(store, sort_keys=True) != before:
        save(store)
    notes, answers = [], {}
    for client, (status, identity, path, new, device) in plans.items():
        label = CLIENTS[client][0]
        if status == "differs":
            notes.append(f"{label}: {path} already has an {NAME} server with another command. "
                         f"Replace that table with:\n{new}")
        elif new is not None:
            try:
                _write(path, new)
            except OSError as exc:
                status, failed = "failed", True
                notes.append(f"{label}: {exc}")
        if device:
            notes.append(f"{label} also starts the projector service (irisgreen-mcp-server). Only the "
                         f"receiver may hold Bluetooth; remove that server from {path}.")
        if status not in ("failed", "differs"):
            answers[identity] = _receiver(store["agents"][identity], store["port"])
        print(f"{label:<16}{status:<11}{path}")
    print(f"{'Credentials':<27}{store_path()}")
    for note in notes:
        print(f"! {note}")
    unknown = sorted(identity for identity, answer in answers.items() if answer == "rejects")
    if "down" in answers.values():
        print(f"No receiver on port {store['port']}. Start one: python -m agent_status.http "
              "--preview irisgreen_data/status.png (add --device ADDRESS to project).")
    elif unknown:
        print(f"The receiver on port {store['port']} does not know {', '.join(unknown)}. Restart it once; "
              "from then on it follows the credential store without a restart.")
    elif answers:
        print(f"The receiver on port {store['port']} accepts {', '.join(sorted(answers))}.")
    print(f"Reload each client so it starts {NAME}.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
