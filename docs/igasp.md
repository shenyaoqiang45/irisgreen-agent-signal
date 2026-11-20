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

Start **one receiver** shared by all agents. In PowerShell, for one agent:

```powershell
$env:IGASP_AGENT = "codex"
$env:IGASP_TOKEN = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$env:IGASP_CREDENTIALS = @{codex=$env:IGASP_TOKEN} | ConvertTo-Json -Compress
.\.venv\Scripts\python.exe -m agent_status.http --preview irisgreen_data\status.png
```

Generate a different token for each additional identity in `IGASP_CREDENTIALS`.
Keep that mapping private to the receiver. Give a client **only its own**
`IGASP_AGENT` and `IGASP_TOKEN` via its local secret/environment configuration.
Do not commit tokens. Preview files may contain private task information; keep
them in an operator-controlled directory.

Register a **stdio** server named `irisgreen-status` in Cursor or Codex:

| Setting | Value |
|---|---|
| Command | Absolute path to the repo's `.venv\Scripts\python.exe` |
| Arguments | One absolute path to `mcp\irisgreen-agent-status\launch.py` |
| Environment passed to server | `IGASP_AGENT`, `IGASP_TOKEN`, optional `IGASP_PORT` (default `8171`) |

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
| `agent.expression` | `report_expression` | ID defaults to event ID (returned in receipt); supplying an expression ID replaces that notice. |
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

The running receiver connects once and keeps its MCP client and device session
for subsequent reports. It uploads a replacement without first clearing the
display. An idle Bluetooth link may still drop independently; the existing
device layer reconnects if needed before an upload. Hardware playback is capped
at one hour, so a running receiver renews a persistent frame before it expires.
Stopping the receiver intentionally clears and disconnects. Agent-facing HTTP
and MCP acknowledgments confirm receipt, not that projection succeeded.

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
