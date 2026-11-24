# IrisGreen notifications

Follow the IrisGreen reporting instructions in `AGENTS.md` for this repository.
At the end of every conversation turn, project one short summary of that turn's
important information: outcomes, findings, blockers, and decisions. Write every
projected summary in English. Prefer
`report_expression` through the configured `irisgreen-status` MCP service, with
one stable session ID and no duration or ttl, so the message stays until the
next one replaces it. If that tool is not available in the session, send the
same summary from a shell:
`.venv/Scripts/python.exe -m agent_status.report --agent copilot --session <id> "<title>" "<body>"`.
Both paths speak HTTP only. Do not start the device service or call its tools;
only the IGASP receiver may hold Bluetooth. The display clears and disconnects
after five minutes without a successful projection. Never project secrets or
private reasoning. If neither path is accepted, tell the user in chat instead
of claiming the wall showed the message.
