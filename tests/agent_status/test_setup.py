import json
import queue
import secrets
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from threading import Thread

import pytest
from mcp.client.session import CLIENT_CAPABILITIES_META_KEY, CLIENT_INFO_META_KEY, PROTOCOL_VERSION_META_KEY

from agent_status import report, setup
from agent_status.credentials import issue, load, save, store_path
from agent_status.http import make_server

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def home(tmp_path, monkeypatch):
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(tmp_path))
    for name in ("IGASP_HOME", "IGASP_AGENT", "IGASP_TOKEN", "IGASP_PORT", "IGASP_SESSION",
                 "CODEX_HOME", "COPILOT_HOME"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def receiver(home):
    """A running receiver that follows the store; one identity lets it start."""
    issue("seed")
    with make_server({}, 0, home / "out.png", store=store_path()) as server:
        save({**load(), "port": server.server_port})
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": .05})
        worker.start()
        try:
            yield server
        finally:
            server.shutdown()
            worker.join()


def shows(server, title):
    for _ in range(100):
        if server.latest and server.latest[0] and server.latest[0].lines[1] == title:
            return True
        time.sleep(.05)
    return False


def test_setup_gives_each_client_an_identity_and_leaves_its_configuration_alone(home, receiver, capsys):
    inline = secrets.token_urlsafe(32)
    cursor = home / ".cursor" / "mcp.json"
    cursor.parent.mkdir()
    cursor.write_text(json.dumps({"mcpServers": {
        "other": {"url": "https://example.test"},
        "irisgreen-status": {"command": "python", "args": ["launch.py"],
                             "env": {"IGASP_AGENT": "cursor", "IGASP_TOKEN": inline}}}}))
    untouched = cursor.read_bytes()
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir()
    original = (b'model = "x"\r\n\r\n[mcp_servers.irisgreen]\r\ncommand = "python"\r\n'
                b"args = ['C:\\repo\\mcp\\irisgreen-mcp-server\\launch.py']\r\n")
    codex.write_bytes(original)
    copilot = home / ".copilot" / "mcp-config.json"

    assert setup.main([]) == 0
    out = capsys.readouterr().out
    agents = load()["agents"]
    assert agents["cursor"] == inline and cursor.read_bytes() == untouched
    assert len({agents[name] for name in ("cursor", "codex", "copilot")}) == 3
    # Issued while the receiver was already running: it accepts them without a restart.
    assert "accepts codex, copilot, cursor" in out
    assert "Codex also starts the projector service" in out

    written = codex.read_bytes()
    assert written.startswith(original) and b"\n" not in written.replace(b"\r\n", b"")
    entry = tomllib.loads(written.decode())["mcp_servers"]["irisgreen-status"]
    assert entry["args"][-2:] == ["--agent", "codex"] and Path(entry["args"][0]).is_file()
    entry = json.loads(copilot.read_text())["mcpServers"]["irisgreen-status"]
    assert entry["type"] == "stdio" and entry["args"][-2:] == ["--agent", "copilot"]
    assert not any(agents[name] in path.read_text() for name, path in (("codex", codex), ("copilot", copilot)))

    files = [path.read_bytes() for path in (cursor, codex, copilot)]
    assert setup.main([]) == 0
    assert files == [path.read_bytes() for path in (cursor, codex, copilot)] and load()["agents"] == agents


def test_shell_and_mcp_reports_use_the_stored_identity(home, receiver, capsys):
    issue("copilot")
    assert report.main(["--agent", "copilot", "--session", "s", "Built", "All tests pass"]) == 0
    assert shows(receiver, "Built")
    assert report.main(["--agent", "stranger", "Not registered"]) == 1
    assert "agent_status.setup" in capsys.readouterr().out

    proc = subprocess.Popen([sys.executable, str(ROOT / "mcp/irisgreen-agent-status/launch.py"),
                             "--agent", "copilot"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, encoding="utf-8")
    replies = queue.Queue()
    Thread(target=lambda: [replies.put(json.loads(line)) for line in proc.stdout], daemon=True).start()

    def call(rid, method, params):
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n")
        proc.stdin.flush()
        while True:
            reply = replies.get(timeout=30)
            if reply.get("id") == rid:
                return reply

    client = {"name": "probe", "version": "0"}
    try:
        # VS Code Copilot probes server/discover, then falls back to the handshake.
        # That handshake must still be accepted.
        probe = call(1, "server/discover", {"_meta": {PROTOCOL_VERSION_META_KEY: "2026-07-28",
                                                      CLIENT_INFO_META_KEY: client,
                                                      CLIENT_CAPABILITIES_META_KEY: {}}})
        assert "error" in probe
        handshake = call(2, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                           "clientInfo": client})
        assert handshake["result"]["protocolVersion"] == "2025-11-25"
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        result = call(3, "tools/call", {"name": "report_expression", "arguments": {
            "session_id": "s", "expression": {"intent": "completed", "title": "From MCP"}}})["result"]
        assert not result.get("isError"), result
        assert shows(receiver, "From MCP")
    finally:
        proc.stdin.close()
        proc.wait(timeout=15)
