"""Lightweight single-process pub/sub Event Bus."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, List
from uuid import uuid4

from visualizer.event_bus.event import Event

EventHandler = Callable[[Event], None]


@dataclass(frozen=True)
class Subscription:
    """Token returned by :meth:`EventBus.subscribe`."""

    subscription_id: str
    pattern: str


def matches(pattern: str, event_type: str) -> bool:
    """Return True if ``pattern`` selects ``event_type``.

    Accepted forms:
    * ``"*"`` — every event
    * exact type, e.g. ``"music.playback"``
    * prefix with a trailing dot or star, e.g. ``"music."`` or ``"visual.*"``
    * bare prefix, e.g. ``"music"`` matches ``music`` and ``music.*``
    """
    if pattern in ("*", ""):
        return True
    if pattern.endswith("*"):
        return event_type.startswith(pattern[:-1])
    if pattern.endswith("."):
        return event_type.startswith(pattern)
    if event_type == pattern:
        return True
    return event_type.startswith(pattern + ".")


class EventBus:
    """Synchronous in-process Event Bus.

    ``publish`` delivers to current subscribers immediately, in
    subscription order. Handlers may publish additional events; those
    are delivered after the current handler returns (re-entrant publish
    is supported). This is not a distributed queue.
    """

    def __init__(self) -> None:
        self._subs: List[tuple[Subscription, EventHandler]] = []
        self._sequence = 0

    def subscribe(self, pattern: str, handler: EventHandler) -> Subscription:
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("pattern must be a non-empty string")
        if not callable(handler):
            raise ValueError("handler must be callable")
        sub = Subscription(subscription_id=uuid4().hex, pattern=pattern)
        self._subs.append((sub, handler))
        return sub

    def unsubscribe(self, subscription: Subscription) -> bool:
        before = len(self._subs)
        self._subs = [item for item in self._subs if item[0] != subscription]
        return len(self._subs) < before

    def publish(self, event: Event) -> Event:
        if not isinstance(event, Event):
            raise TypeError("publish expects an Event")
        if event.sequence is None:
            self._sequence += 1
            event = replace(event, sequence=self._sequence)
        # Copy the list so subscribe/unsubscribe during delivery is safe.
        for sub, handler in list(self._subs):
            if matches(sub.pattern, event.type):
                handler(event)
        return event

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)
