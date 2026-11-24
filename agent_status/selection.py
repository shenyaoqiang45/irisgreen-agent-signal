"""Project the Chinese gloss of the English word or short sentence under the cursor."""

import re

from .protocol import envelope
from .receiver import Rejected

SESSION = "selection"
EXPRESSION = "selection"
HOLD_MS = 60000
LIMIT = 160

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_CJK = re.compile(r"[\u3400-\u9fff]")
_SPACE = re.compile(r"\s+")


def accept(text):
    """Return a short English selection, or empty when it should not be translated."""
    text = _SPACE.sub(" ", text or "").strip()
    if not text or len(text) > 140:
        return ""
    if len(re.findall(r"[.?!](?:\s|$)", text)) > 1:
        return ""
    words = _WORD.findall(text)
    if not words or len(words) > 24:
        return ""
    if _CJK.search(text):
        return ""
    letters = sum(len(word) for word in words)
    if letters / max(len(_SPACE.sub("", text)), 1) < 0.55:
        return ""
    return text


def project_selection(receiver, agent, body):
    if not isinstance(body, dict) or set(body) - {"text", "translation"}:
        raise Rejected(400, "expected text and translation")
    source = accept(body.get("text") if isinstance(body.get("text"), str) else "")
    chinese = _clip(body.get("translation") if isinstance(body.get("translation"), str) else "")
    if not source or not chinese or not _CJK.search(chinese) or chinese == source:
        return {"ok": True, "skipped": True}
    payload = {"intent": "discovery", "expression_id": EXPRESSION,
               "title": _clip(source), "message": chinese,
               "ttl_ms": HOLD_MS, "duration_ms": HOLD_MS}
    receipt = receiver.receive(envelope("agent.expression", agent, SESSION, payload), agent)
    return {"ok": True, "event_id": receipt["event_id"],
            "expression": {"title": payload["title"], "message": payload["message"]}}


def _clip(value, limit=LIMIT):
    value = re.sub(r"[\u200b-\u200d\ufeff]", "", value or "")
    value = re.sub(r"[\u0000-\u001f\u007f]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[:limit - 1].rstrip() + "…"
