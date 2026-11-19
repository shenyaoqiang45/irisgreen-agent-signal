# IrisGreen reporting

When an agent working in this repository has an important finding, a blocker,
needs the user's decision or approval, or completes a meaningful task, it must
proactively send a short, non-sensitive summary to IrisGreen. Do not wait for
the user to ask for a projection. Do not project secrets, private reasoning,
or information unsuitable for a shared wall.

Prefer the configured `irisgreen-status` MCP `report_expression` tool with a
stable session ID. Omit `duration_ms` and `ttl_ms` so the message remains until
the next expression replaces it. Report only relevant changes, not every token
or routine tool call. An acknowledgment is not authorization.

Reuse the device connection during the interaction. Do not clear the display
or disconnect after each message; clear when explicitly requested or at session
shutdown. If the reporting service or device is unavailable, say so in chat;
do not claim a message was projected based only on an HTTP/MCP receipt. Follow
the operator's device safety instructions. See `docs/igasp.md` for setup.
