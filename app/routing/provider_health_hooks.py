from __future__ import annotations

from collections import defaultdict


class ProviderHealthHooks:
    def __init__(self) -> None:
        self._stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"success": 0, "fail": 0}
        )

    def mark_success(self, provider: str) -> None:
        self._stats[provider]["success"] += 1

    def mark_failure(self, provider: str) -> None:
        self._stats[provider]["fail"] += 1

    def availability_boost(self, provider: str) -> float:
        s = self._stats[provider]
        total = s["success"] + s["fail"]
        if total == 0:
            return 0.0
        ratio = s["success"] / total
        return (ratio - 0.5) * 8.0

    def snapshot(self) -> dict[str, dict[str, int]]:
        return dict(self._stats)


_provider_health_hooks = ProviderHealthHooks()


def get_provider_health_hooks() -> ProviderHealthHooks:
    return _provider_health_hooks

