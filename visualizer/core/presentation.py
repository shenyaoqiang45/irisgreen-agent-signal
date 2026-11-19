"""Domain-neutral wall-clock scene selection (lower priorities win)."""

from dataclasses import dataclass
from math import inf


@dataclass(frozen=True)
class Card:
    lines: tuple[str, ...]
    priority: int
    revision: int
    until: float = inf
    pulse: float = 0.0
    accent: int = 0


def select(cards, now):
    return min((card for card in cards if card.until > now),
               key=lambda card: (card.priority, -card.revision), default=None)
