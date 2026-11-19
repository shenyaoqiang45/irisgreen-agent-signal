"""Shared Event schema and clock-aware helpers.

Mandatory fields: type, source, payload, clock, timestamp_ms.
Optional fields: event_id, sequence, priority, media_session_id.

Clock rules used throughout this package:

* ``music.playback``, ``music.lyrics``, and all ``visual.*`` timeline
  events use ``clock="media"``. ``timestamp_ms`` is the media playback
  position in milliseconds.
* ``music.audio_features`` and ``music.beat`` use ``clock="capture"``.
  ``timestamp_ms`` is the capture clock. When a Playback Clock is
  available, the estimated media position belongs in
  ``payload["playback_position_ms"]``. Never write the capture clock
  into a media-clock field.
* ``PlaybackClock.last_sync_timestamp`` is wall time (milliseconds).
* Orchestration and the animation timeline always use the media clock.
  When consuming a capture-clock event, read
  ``payload["playback_position_ms"]``, not ``timestamp_ms``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

VALID_CLOCKS = frozenset({"media", "capture", "wall"})


def _require_non_empty_str(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timestamp(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("timestamp_ms must be a number")
    if value < 0:
        raise ValueError("timestamp_ms must be >= 0")
    return value


def _require_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("payload must be a mapping")
    return dict(value)


@dataclass(frozen=True)
class Event:
    """Validated, immutable event on the in-process bus."""

    type: str
    source: str
    payload: dict[str, Any]
    clock: str
    timestamp_ms: int | float
    event_id: str | None = None
    sequence: int | None = None
    priority: int | None = None
    media_session_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_str("type", self.type)
        _require_non_empty_str("source", self.source)
        object.__setattr__(self, "payload", _require_payload(self.payload))
        if self.clock not in VALID_CLOCKS:
            raise ValueError(
                f"clock must be one of {sorted(VALID_CLOCKS)}, got {self.clock!r}"
            )
        _require_timestamp(self.timestamp_ms)
        if self.event_id is not None and not isinstance(self.event_id, str):
            raise ValueError("event_id must be a string when provided")
        if self.sequence is not None and (
            isinstance(self.sequence, bool) or not isinstance(self.sequence, int)
        ):
            raise ValueError("sequence must be an int when provided")
        if self.priority is not None and (
            isinstance(self.priority, bool) or not isinstance(self.priority, int)
        ):
            raise ValueError("priority must be an int when provided")
        if self.media_session_id is not None and not isinstance(
            self.media_session_id, str
        ):
            raise ValueError("media_session_id must be a string when provided")

    @classmethod
    def create(
        cls,
        type: str,
        source: str,
        payload: Mapping[str, Any],
        clock: str,
        timestamp_ms: int | float,
        *,
        event_id: str | None = None,
        sequence: int | None = None,
        priority: int | None = None,
        media_session_id: str | None = None,
    ) -> "Event":
        """Build an event, filling ``event_id`` when the caller omits it."""
        return cls(
            type=type,
            source=source,
            payload=dict(payload),
            clock=clock,
            timestamp_ms=timestamp_ms,
            event_id=event_id or uuid4().hex,
            sequence=sequence,
            priority=priority,
            media_session_id=media_session_id,
        )


def media_time_ms(event: Event) -> float | None:
    """Media-clock position for an event, or None if it cannot be placed.

    For ``clock="media"`` this is ``timestamp_ms``. For capture-clock events
    this is ``payload["playback_position_ms"]`` only — never the capture
    timestamp.
    """
    if event.clock == "media":
        return float(event.timestamp_ms)
    position = event.payload.get("playback_position_ms")
    if position is None:
        return None
    if isinstance(position, bool) or not isinstance(position, (int, float)):
        return None
    return float(position)
