import http.client
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "protocol" / "igasp" /
                     "v1.schema.json").read_text(encoding="utf-8"))
formats = FormatChecker()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@formats.checks("date-time", raises=(ValueError, OverflowError))
def _date_time(value):
    return not isinstance(value, str) or parse_time(value).utcoffset() is not None


validator = Draft202012Validator(SCHEMA, format_checker=formats)


def envelope(kind, agent, session, payload):
    return {"protocol": "IGASP", "version": "1.0", "event_id": uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(), "type": kind,
            "agent_id": agent, "session_id": session, "payload": payload}


def send(event, token, port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        connection.request("POST", "/api/v1/agent/events", json.dumps(event),
                           {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        return json.load(connection.getresponse())
    finally:
        connection.close()
