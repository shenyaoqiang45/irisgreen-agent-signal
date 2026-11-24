# IrisGreen Agent Status Protocol (IGASP 1.0)

An agent reports what it wants to show. The receiver neither monitors the agent
runtime nor infers mood, personality, progress or ETA. Text is display data,
not instructions. Acknowledging a notification **does not authorize an action**.

## Try the seven-step scenario

From the repository root with its Python dependencies installed:

```powershell
.\.venv\Scripts\python.exe -m agent_status.demo --simulate-device
```

Inspect the seven PNGs in `irisgreen_data/igasp`: idle, thinking, working,
discovery, approval, resumed, completed. This uses the real renderer and device
MCP client but a **simulated projector**.

## Connect a real agent (preview only by default)

Register the reporter with Cursor, Codex and VS Code Copilot, then start **one
receiver** shared by all agents:

```powershell
.\.venv\Scripts\python.exe -m agent_status.setup
.\.venv\Scripts\python.exe -m agent_status.http --preview irisgreen_data\status.png
```

`setup` gives each client its own identity (`cursor`, `codex`, `copilot`) and
token, kept in `~/.irisgreen/credentials.json` (`IGASP_HOME` moves it). It adds
a stdio server named `irisgreen-status` to the client's user-level file, so the
client can report from any workspace:

| Client | File | Entry |
|---|---|---|
| Cursor | `~/.cursor/mcp.json` | `mcpServers` |
| Codex (CLI, IDE extension, desktop app) | `~/.codex/config.toml` | `[mcp_servers.irisgreen-status]` |
| VS Code Copilot, Copilot CLI | `~/.copilot/mcp-config.json` | `mcpServers` |

Each entry runs `mcp/irisgreen-agent-status/launch.py --agent <identity>` with
the interpreter that ran `setup`. No token is written to a client file; the
reporter reads its own from the store on each call. The rest of the file is
preserved, and an entry that already carries `IGASP_TOKEN` is kept and its
token recorded. Name clients to limit the run (`agent_status.setup codex`).
Running it again changes nothing. `setup` ends by asking the running receiver
whether it knows each identity. Reload a client afterwards.

The receiver reads the same store and rereads it when the file changes, so a
later `setup` needs no restart. `IGASP_CREDENTIALS`, a JSON object of identity
to token, still works and adds to the store. A reporter can likewise be given
`IGASP_AGENT`, `IGASP_TOKEN` and optionally `IGASP_PORT` instead of `--agent`.
Do not commit tokens. Preview files may contain private task information; keep
them in an operator-controlled directory.

VS Code Copilot reads `~/.copilot/mcp-config.json` and a workspace-root
`.mcp.json`; it does not read `.vscode/mcp.json` directly. Its client probes
`server/discover` and then falls back to the `initialize` handshake. The
reporter therefore serves the handshake protocol only: the SDK default answers
the probe and then refuses the handshake, and the connection fails.

An agent that has a shell but no MCP tools reports the same way:

```powershell
.\.venv\Scripts\python.exe -m agent_status.report --agent copilot --session chat-1 "Tests pass" "Ready to merge"
```

It prints the receipt and exits non-zero when the report was not accepted.

Use the reporting server **instead of** the projector-control MCP for agents
that should only report status. No working-directory assumption or BLE
permission is necessary for the reporter. To smoke-test the receiver without
an agent UI, run `python -m agent_status.demo --http` in an environment with
the corresponding client credentials. Watch the receiver's `status.png`;
the demo's seven saved files are a separate local replay.

The repository supplies proactive-reporting instructions in `AGENTS.md`, the
Cursor always-on rule, Copilot project instructions, and the MCP server
instructions. Agents should report important discoveries, blockers, decisions
and meaningful completions without waiting to be prompted. These are client
instructions, not a way to force an agent or client to obey: enable the rule
and MCP tools in the client, configure its credentials, run the receiver with
device output enabled, and verify in that client. An HTTP/MCP receipt confirms
the report was accepted, not that the projector displayed it. Surface delivery
failures in chat.

Suggested agent instructions:

> Pick one session ID per conversation. Report major state changes, tasks and
> important notices, not every token. Declare style or mood only if useful.
> Omit unreliable progress/ETA. Do not send private reasoning or secrets.
> Keep an approval request distinct from the user's actual approval.
> Use `report_expression` without `duration_ms` or `ttl_ms` for messages to
> the user; keep a stable session ID. Do not clear the display or disconnect
> after each report. A new expression replaces the previous message.

## Wire contract and lifecycle

[JSON Schema](../protocol/igasp/v1.schema.json) ·
[Example snapshot](../protocol/igasp/example.snapshot.json).
Every write is an envelope, with the business fields **directly** in `payload`.
For example:

```json
{"protocol":"IGASP","version":"1.0","event_id":"evt_001","agent_id":"codex","session_id":"s1",
 "type":"agent.status","timestamp":"2026-11-19T08:00:00Z","payload":{"state":"working","mood":"focused"}}
```

HTTP accepts JSON POSTs at `127.0.0.1:8171` with `Authorization: Bearer <token>`.
`/api/v1/page/open` accepts `{"url","title","text"}` for the foreground page the
user just opened. The receiver keeps the opening sentence, at most 160
characters, as one `agent.expression` in session `browser`. The next page
replaces it. Give this caller its own credential, for example `"browser"`.
The extension in `extensions/page-glance` posts that body when a page finishes
loading in the active tab. The same extension watches the mouse selection.
A short word, phrase, or sentence in any language is translated to Chinese and posted
to `/api/v1/selection` as `{"text","translation"}`. The receiver shows that
pair for 60 seconds in session `selection`, replacing the previous selection.
The same text is not sent again. Text the translator detects as Chinese, long passages, and more than one
sentence are ignored. Clicking a fruit or vegetable picture posts the label on that picture
(its alt text, caption, or file name) to `/api/v1/produce` as `{"hint"}`.
A known item is shown for 60 seconds as its Chinese name and kilocalories per 100 g.
An opened photo still sits in front of that card. Leaving for another address clears it.
On X, opening a status photo
(`/status/<id>/photo/<n>`) posts that picture to `/api/v1/media` as
`{image_base64}`. The receiver letterboxes it onto the 640×480 field and lights only
pixels brighter than 127. Near-black stays off, and so does the letterbox. The picture
stays in front of the page sentence until the viewer closes. `{"clear": true}` removes it. Leaving for another address
clears it too.
The extension asks the Edge translation endpoint first
and caches repeats, so a second look at the same word does not call out again.
`extensions/vscode-selection` does the same thing inside VS Code and Cursor:
the editor selection event replaces the browser mouse listener, and the
Chinese gloss still posts to `/api/v1/selection`. It reads the receiver token
from `irisgreen.token`, or from `~/.cursor/irisgreen-status.json` when that
setting is empty.
`/api/v1/agent/events` accepts any IGASP event. `/api/v1/agent/snapshot` accepts
only snapshot envelopes. POST `{"session_id":"s1"}` to `/api/v1/agent/snapshot/read`
to export the authenticated agent's current session as a replayable snapshot.
Keep exported snapshots if recovery across process restarts is required: state
and deduplication are in memory. The protocol is not a durable event log.

| Event | MCP tool | Semantics |
|---|---|---|
| `agent.profile`, `agent.personality` | `report_profile`, `report_personality` | Replace profile or just personality across this agent's sessions. MBTI/custom style is self-declared. |
| `agent.status`, `agent.status.clear` | `report_status`, `clear_status` | Patch only supplied fields; `mood:null` clears mood without changing state. Clear removes the whole status, not tasks. |
| `agent.task` | `report_task` | Upsert by task ID. Each report replaces the task. Progress is a supplied percentage (0–100), not an estimate from elapsed time. Terminal tasks leave the active set and briefly display their outcome. |
| `agent.expression` | `report_expression` | ID defaults to event ID (returned in receipt); supplying an expression ID replaces that notice. Optional `image_base64` is one PNG, JPEG, BMP, or WebP (standard base64, at most 60000 characters) shown in place of the text card. |
| `agent.expression.ack`, `agent.expression.clear` | `ack_expression`, `clear_expression` | Remove that notification in that session. |
| `agent.snapshot` | `report_snapshot` | Atomically replace one session's status, active tasks, live expressions and the agent's shared profile. Restored notices retain their original timestamp. |
| `agent.session.started`, `agent.session.ended` | `start_session`, `end_session` | Sessions can also start on first report. Ending drops transient state but retains profile. |

MCP creates the envelope, source identity, timestamp and event ID. Reports
take `session_id` plus the corresponding record (e.g. `status` or `expression`).
For HTTP retries reuse the same event ID and contents. The last 1024 accepted
events deduplicate by agent and event ID; conflicting ID reuse is rejected.
Updates apply in **arrival order**, not sender clock order. Use ordered writers
per session; request a fresh snapshot after a missed sequence.

Omit both `duration_ms` and `ttl_ms` for proactive messages: the notice stays
until the next expression in that agent/session replaces it, or it is
explicitly acknowledged/cleared. Status, task and profile reports and duplicate
retries do not dismiss it. Other sessions' higher-priority notices can still
preempt it; ending a session removes its messages.
For temporary notices, `duration_ms` limits display and `ttl_ms` limits validity
(default 60 s when only duration is supplied). Both start at the earlier of event time and
receipt, so stale notices do not get a fresh display window on arrival.
The renderer returns to the next eligible card without waiting for another report.
The receiver limits authenticated identities to 30 requests/s each, bodies
to 64 KiB, active sessions to 128 and tasks/expressions to 32 each per session.
Clients should treat 400 as invalid input, 401/403 as credential/identity errors,
409 as a conflict and 429 as a reason to back off.

## Presentation and physical acceptance

Ingress → snapshot manager → in-process event bus → agent visual mapping →
wall-clock card selector → binary 640×480 renderer. Agent cards rank urgent,
attention, expression, task, then ambient. Music integration is out of scope,
not an outstanding acceptance item. A receiver embedder can pass `priorities`
to `make_server`.
Equal-priority sessions favor the most recently updated one. Declared style
changes the ambient ring geometry; state and mood modulate its movement.
The current card renderer uses a source header and left-aligned text in a
uniform font size and line spacing. It targets 48 px, wrapping lines and
reducing the whole card's font size together when needed; if the card
still exceeds the field at the minimum size, an ellipsis indicates that content
was omitted and the complete message remains available in the agent's chat.
This is the current implementation, not a fixed style for future expressions.
An expression that includes `image_base64` is scaled to fill the 640×480 field and thresholded at 127, so the wall shows that picture. The same 64 KiB event limit applies; the field cap keeps one image inside it. A path is not an input.

Add **one** output option to the receiver command. Omit `--seconds` for
continuous operation; Ctrl+C clears and disconnects. Bounded test examples:

* `--simulate-device --seconds 60`: exercise the live adapter with simulated hardware.
* `--device <BLE-address> --seconds 60`: **physical projection**. Only run
  with exclusive access to that projector, an appropriate matte surface, and a
  clear light path. This replaces group-1 content. The operator, not the
  reporting agent, chooses the device and enables projection.

Provide reports while the receiver runs. Use a notice duration long enough to
cover the several-second hardware upload; the wall cannot reproduce preview
frame rate. The output samples the latest scene rather than queueing every
transition. It attempts clear and disconnect on shutdown. Confirm content,
orientation, readability and final darkness **by eye**; a transport receipt
does not verify any of these.

The running receiver keeps its MCP client and uploads replacements without
first clearing the display. The device MCP server starts a five-minute idle
timer at connection and resets it after each successful projection, not on
status queries, failed projections or repeated connect calls. On expiry it
attempts to clear and disconnect, logging failures to stderr. The receiver does
not replay an old card to keep the device awake; a subsequent new card
reconnects and projects. The expression remains in the receiver's state until
replaced or cleared even though its physical display has gone dark. Stopping
the receiver attempts to clear and disconnect. A crashed or forcibly terminated
process cannot guarantee cleanup. Restart existing device MCP processes to
load the timer. Agent-facing HTTP and MCP acknowledgments confirm receipt, not
that projection succeeded.

**2026-11-19 verification:** Actual device MCP connected to
`20:6E:F1:81:71:62`; manufacturer `AINSTEC`, firmware `36130326071700`,
MTU 512, `projecting:false`; disconnect succeeded. A separate read-only
`verify_pc.py` run against the same address finished with zero failures:
advertisement, GATT service and characteristic properties, firmware, battery
read and disconnect passed; one notification arrived in four seconds. Model
and serial read as empty (warnings). Neither check uploaded a frame or
requested projection. In a subsequent live test the agent sent an authenticated
HTTP `agent.expression` (`85194e9ef2ae4e39820a80be0aad39ad`). The receiver's
rendered PNG was passed to the device MCP. The tool reported 8463 lit pixels
and 8 seconds of playback; the on-site user confirmed seeing the projection.
Clear returned OK, status then reported `projecting:false`, and disconnect
succeeded. This verifies one agent-authored expression on hardware, not the
seven-stage sequence (simulator only), unattended live forwarding, or the
status-server integration in the actual Cursor and Codex UIs.

**2026-11-24 verification:** `agent_status.setup` ran on a Windows machine with
Cursor, Codex and VS Code Copilot. Codex CLI 0.171 listed `irisgreen-status` as
enabled. The command from each of the three client files was then started by a
scripted MCP client and reported to a preview-only receiver; all three were
accepted under their own identity, as was `agent_status.report`. A raw stdio
client that sent `server/discover` and then `initialize` connected and listed
the tools; before the handshake-only change the same sequence was refused with
`-32022`. After the receiver was restarted with `--device`, a VS Code Copilot
session loaded the tool and its `report_expression` was accepted; the card the
receiver rendered for the projector named `copilot` and carried the message.
Not yet done: the same call from inside Cursor and Codex, and confirmation by
eye that the wall showed these cards.
