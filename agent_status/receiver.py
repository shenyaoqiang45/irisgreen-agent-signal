"""Single-writer snapshot manager. All ingress is validated before publication."""

import time
from math import inf
from collections import OrderedDict, defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field

from visualizer.event_bus import Event, EventBus

from .protocol import envelope, parse_time, validator


class Rejected(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


@dataclass
class Session:
    status: dict = field(default_factory=dict)
    tasks: dict = field(default_factory=dict)
    expressions: dict = field(default_factory=dict)
    changed: int = 0
    finished_task: tuple | None = None


class Receiver:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.bus = EventBus()
        self.profiles = {}
        self.sessions = {}
        self.seen = OrderedDict()
        self.requests = defaultdict(deque)
        self.sequence = 0

    def admit(self, agent):
        now = time.monotonic()
        window = self.requests[agent]
        while window and window[0] <= now - 1:
            window.popleft()
        if len(window) >= 30:
            raise Rejected(429, "report rate exceeded")
        window.append(now)

    def prune(self):
        now = self.clock()
        for s in self.sessions.values():
            for key, entry in list(s.expressions.items()):
                if now >= entry["expires"]:
                    del s.expressions[key]

    def _notice(self, p, stamp, eid):
        start = min(self.clock(), parse_time(stamp).timestamp())
        ttl = p.get("ttl_ms", 60000 if "duration_ms" in p else inf) / 1000
        return {**p, "expression_id": p.get("expression_id", eid), "timestamp": stamp,
                "expires": start + ttl, "display_until": start + min(ttl, p.get("duration_ms", inf) / 1000),
                "revision": self.sequence + 1}

    def snapshot(self, agent, session):
        self.prune()
        s = self.sessions.get((agent, session))
        if s is None:
            raise Rejected(404, "unknown session")
        notices = [{"timestamp": n["timestamp"], "expression": {
            k: v for k, v in n.items() if k not in ("timestamp", "expires", "display_until", "revision")}}
                   for n in s.expressions.values()]
        return envelope("agent.snapshot", agent, session, deepcopy({
            "profile": self.profiles.get(agent, {}), "status": s.status or None,
            "tasks": list(s.tasks.values()), "expressions": notices}))

    def receive(self, event, agent):
        if not isinstance(event, dict) or event.get("agent_id") != agent:
            raise Rejected(403, "agent identity mismatch")
        error = next(validator.iter_errors(event), None)
        if error:
            raise Rejected(400, f"invalid IGASP field: {error.json_path} ({error.validator})")
        key = agent, event["session_id"]
        eid, kind, stamp = event["event_id"], event["type"], event["timestamp"]
        receipt = {"ok": True, "event_id": eid}
        if (agent, eid) in self.seen:
            if self.seen[agent, eid] != event:
                raise Rejected(409, "event_id already used")
            return {**receipt, "duplicate": True}
        p = deepcopy(event["payload"])
        self.prune()
        s = self.sessions.get(key)
        if s is None:
            if kind.endswith((".ack", ".clear", ".ended")):
                raise Rejected(404, "unknown session")
            if len(self.sessions) >= 128:
                raise Rejected(409, "session capacity reached")
            s = Session()
        previous_sticky = {nid for nid, n in s.expressions.items() if n["display_until"] == inf}
        if kind == "agent.profile":
            self.profiles[agent] = p
        elif kind == "agent.personality":
            self.profiles.setdefault(agent, {})["personality"] = p
        elif kind == "agent.status":
            s.status.update(p)
        elif kind == "agent.status.clear":
            s.status.clear()
        elif kind == "agent.task":
            tid = p["task_id"]
            if p["status"] in ("completed", "cancelled", "failed"):
                s.tasks.pop(tid, None)
                s.finished_task = p, self.clock() + 5
            else:
                if tid not in s.tasks and len(s.tasks) >= 32:
                    raise Rejected(409, "task capacity reached")
                s.tasks.pop(tid, None)
                s.tasks[tid] = p
                s.finished_task = None
        elif kind == "agent.expression":
            notice = self._notice(p, stamp, eid)
            nid = notice["expression_id"]
            if nid not in s.expressions and len(s.expressions.keys() - previous_sticky) >= 32:
                raise Rejected(409, "expression capacity reached")
            s.expressions.pop(nid, None)
            s.expressions[nid] = notice
            previous_sticky.discard(nid)
        elif kind in ("agent.expression.clear", "agent.expression.ack"):
            if s.expressions.pop(p["expression_id"], None) is None:
                raise Rejected(404, "unknown or expired expression")
        elif kind == "agent.snapshot":
            tasks = {t["task_id"]: t for t in p["tasks"]}
            notices = {n["expression"]["expression_id"]: self._notice(n["expression"], n["timestamp"], "")
                       for n in p["expressions"]}
            if len(tasks) != len(p["tasks"]) or len(notices) != len(p["expressions"]):
                raise Rejected(400, "duplicate snapshot member id")
            if any(t["status"] not in ("pending", "running", "waiting") for t in tasks.values()):
                raise Rejected(400, "snapshot tasks must be active")
            self.profiles[agent] = p["profile"]
            s = Session(p["status"] or {}, tasks, notices)

        if kind == "agent.expression":
            for nid in previous_sticky:
                s.expressions.pop(nid, None)
        self.sequence += 1
        s.changed = self.sequence
        self.sessions[key] = s
        if kind == "agent.session.ended":
            del self.sessions[key]
        self.seen[agent, eid] = deepcopy(event)
        if len(self.seen) > 1024:
            self.seen.popitem(last=False)
        self.prune()
        self.bus.publish(Event.create(kind, agent, {**event, "received_at": self.clock()},
                                      "wall", self.clock() * 1000, event_id=eid))
        return receipt
