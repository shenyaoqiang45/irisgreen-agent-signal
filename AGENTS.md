# IrisGreen reporting

When an agent working in this repository talks with the user, it must end
every turn by projecting one short, non-sensitive summary of that turn's
important information: outcomes, findings, blockers, and decisions that need
the user. Do not wait for the user to ask for a projection. Do not project
secrets, private reasoning, information unsuitable for a shared wall, or every
token and routine tool call. One summary per turn is enough. Write every
projected summary in English, including the title and body.

Prefer the configured `irisgreen-status` MCP `report_expression` tool with one
stable session ID for the conversation. Omit `duration_ms` and `ttl_ms` so the
message remains until the next expression replaces it in receiver state. The
device clears and disconnects after five minutes without a successful
projection; a new message reconnects it. An acknowledgment is not authorization.

If that tool is not available in your session, send the same summary from a
shell with the repository's interpreter, under your own identity (`cursor`,
`codex` or `copilot`):

```text
.venv/Scripts/python.exe -m agent_status.report --agent <identity> --session <id> "<title>" "<body>"
```

Both paths speak HTTP only. Do not start the device service or call
`device_connect` to deliver the summary. For now only the IGASP receiver may
launch that service and hold Bluetooth. If neither path is accepted, say so in
chat; do not claim a message was projected based only on an HTTP/MCP receipt.
Follow the operator's device safety instructions. `python -m agent_status.setup`
registers the tool and the identities; see `docs/igasp.md`.

Status cards do not need a fixed visual style or template. Choose presentation
appropriate to the message, agent, and device capabilities while keeping it
legible. The current renderer's layout is an implementation, not a requirement
that all future expressions look the same.
