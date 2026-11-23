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

If `report_expression` is unavailable, project the same summary with the device
after `device_connect`, and reuse that connection. Do not clear the display or
disconnect after each message; clear when explicitly requested or at session
shutdown. If the reporting service or device is unavailable, say so in chat;
do not claim a message was projected based only on an HTTP/MCP receipt. Follow
the operator's device safety instructions. See `docs/igasp.md` for setup.

Status cards do not need a fixed visual style or template. Choose presentation
appropriate to the message, agent, and device capabilities while keeping it
legible. The current renderer's layout is an implementation, not a requirement
that all future expressions look the same.
