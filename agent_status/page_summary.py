"""Turn the page the user just opened into one wall sentence."""

import re

from .protocol import envelope
from .receiver import Rejected

SESSION = "browser"
EXPRESSION = "open-page"
LIMIT = 160

_SPLIT = re.compile(r"[。！？!?]\s*|\n+|\.\s+")
_HOST = re.compile(r"^https?://([^/?#]+)")


def summarize(title, text, url=""):
    """Return an expression payload, or None when the page has nothing to show."""
    heading = _clip(title) or _host(url)
    lead = _choose(_parts(text), heading)
    message = _clip(lead or heading)
    if not message:
        return None
    shown = heading if heading and heading != message else (_host(url) or "这一页")
    if shown == message:
        shown = _host(url) or "这一页"
    return {"intent": "discovery", "expression_id": EXPRESSION,
            "title": _clip(shown), "message": message}


def open_page(receiver, agent, body):
    if not isinstance(body, dict) or set(body) - {"url", "title", "text"}:
        raise Rejected(400, "expected url, title, and text")
    url, title, text = body.get("url"), body.get("title"), body.get("text")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")) or len(url) > 2000:
        raise Rejected(400, "expected an http(s) url")
    if not isinstance(title, str) or not isinstance(text, str):
        raise Rejected(400, "expected title and text")
    if len(title) > 300 or len(text) > 8000:
        raise Rejected(400, "page text is too long")
    payload = summarize(title, text, url)
    if payload is None:
        return {"ok": True, "skipped": True}
    receipt = receiver.receive(envelope("agent.expression", agent, SESSION, payload), agent)
    return {"ok": True, "event_id": receipt["event_id"],
            "expression": {"title": payload["title"], "message": payload["message"]}}


def _parts(text):
    return [_clip(part, LIMIT) for part in _SPLIT.split(text or "")]


def _choose(parts, heading):
    prose = [(i, part) for i, part in enumerate(parts) if _usable(part, heading) and len(part) >= 24]
    for cue in ("这篇文章", "本文", "总之", "简单说", "结论", "选型建议"):
        found = next((part for _, part in prose if cue in part), "")
        if found:
            return found
    if prose:
        return _current(prose)
    if len(heading) >= 12:
        return heading
    return next((part for part in parts if _usable(part, heading)), "")


def _current(prose):
    """Use the sentence that starts the latest cluster, so a history list stays off the wall."""
    gap_at = prose[0][0]
    gap = 0
    for (prev, _), (nxt, _) in zip(prose, prose[1:]):
        if nxt - prev > gap:
            gap = nxt - prev
            gap_at = nxt
    if gap >= 4:
        return next(part for i, part in prose if i >= gap_at)
    return prose[0][1]


def _usable(part, heading):
    return len(part) >= 8 and part != heading


def _host(url):
    match = _HOST.match(url or "")
    return match.group(1) if match else ""


def _clip(value, limit=LIMIT):
    value = re.sub(r"[\u200b-\u200d\ufeff]", "", value or "")
    value = re.sub(r"[\u0000-\u001f\u007f]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[:limit - 1].rstrip() + "…"
