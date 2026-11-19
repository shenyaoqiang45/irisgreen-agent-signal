from zlib import crc32

from visualizer.core.presentation import Card, select


PRIORITIES = {"urgent": 0, "attention": 1, "expression": 2, "task": 3, "ambient": 4, "music": 5}


class AgentPresentation:
    def __init__(self, receiver, priorities=None):
        self.receiver = receiver
        self.priorities = {**PRIORITIES, **(priorities or {})}
        self.cards = []
        receiver.bus.subscribe("agent.", lambda _: self.refresh())
        self.refresh()

    def refresh(self):
        cards = []
        for (agent, sid), s in self.receiver.sessions.items():
            profile = self.receiver.profiles.get(agent, {})
            personality = profile.get("personality", {})
            style = personality.get("style") or personality.get("type") or personality.get("description", "")
            accent = crc32(style.encode()) % 12 if style else 0
            source = f"{profile.get('display_name', agent)} / {sid}"
            state = s.status.get("state", "")
            mood = s.status.get("mood") or ""
            pulse = {"idle": 0.6, "thinking": 1, "working": 2}.get(state, 0.8)
            pulse *= {"focused": 0.75, "curious": 1.4}.get(mood, 1)
            has_sticky = any(n["display_until"] == float("inf") for n in s.expressions.values())
            if (s.status or profile) and not has_sticky:
                level = "attention" if state in ("failed", "awaiting_approval") else "ambient"
                cards.append(Card((source, state, s.status.get("activity", ""), mood, style),
                                  self.priorities[level], s.changed, pulse=pulse, accent=accent))
            for task in reversed(s.tasks.values() if not has_sticky else ()):
                progress = task.get("progress")
                cards.append(Card((source, task["title"], task.get("current_step", ""), task["status"],
                                   "" if progress is None else f"{progress:g}%",
                                   task.get("estimated_completion_time") or ""),
                                  self.priorities["task"], s.changed, accent=accent))
            if s.finished_task and not has_sticky:
                task, until = s.finished_task
                level = "attention" if task["status"] == "failed" else "task"
                cards.insert(0, Card((source, task["title"], task["status"]),
                                     self.priorities[level], s.changed, until, accent=accent))
            for n in s.expressions.values():
                level = ("urgent" if n.get("urgency") == "urgent" else
                         "attention" if n["intent"] == "approval_required" else "expression")
                cards.insert(0, Card((source, n["title"], n["intent"], n.get("message", ""), n.get("icon", "")),
                                     self.priorities[level], n["revision"], n["display_until"], accent=accent))
        self.cards = cards

    def current(self, other_cards=()):
        return select((*self.cards, *other_cards), self.receiver.clock())
