from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import time


@dataclass(frozen=True)
class FallbackEvent:
    provider: str
    reason: str
    timestamp: float


class FallbackManager:
    def __init__(self, max_events: int = 200) -> None:
        self._events: deque[FallbackEvent] = deque(maxlen=max_events)

    def record(self, provider: str, reason: str) -> None:
        self._events.append(
            FallbackEvent(provider=provider, reason=reason[:160], timestamp=time())
        )

    def recent(self, limit: int = 20) -> list[FallbackEvent]:
        if limit <= 0:
            return []
        return list(self._events)[-limit:]

    def health_penalty(self, provider: str, within_seconds: int = 300) -> float:
        now = time()
        failures = 0
        for ev in self._events:
            if ev.provider == provider and now - ev.timestamp <= within_seconds:
                failures += 1
        return min(12.0, failures * 2.0)


_fallback_manager = FallbackManager()


def get_fallback_manager() -> FallbackManager:
    return _fallback_manager

