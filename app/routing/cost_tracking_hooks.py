from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class CostAggregate:
    requests: int = 0
    estimated_tokens: int = 0
    estimated_cost_usd: float = 0.0


class CostTrackingHooks:
    def __init__(self) -> None:
        self._by_provider: dict[str, CostAggregate] = defaultdict(CostAggregate)

    def track(self, provider: str, estimated_tokens: int, estimated_cost_usd: float) -> None:
        agg = self._by_provider[provider]
        agg.requests += 1
        agg.estimated_tokens += max(0, estimated_tokens)
        agg.estimated_cost_usd += max(0.0, estimated_cost_usd)

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        return {
            provider: {
                "requests": agg.requests,
                "estimated_tokens": agg.estimated_tokens,
                "estimated_cost_usd": round(agg.estimated_cost_usd, 6),
            }
            for provider, agg in self._by_provider.items()
        }


_cost_tracking_hooks = CostTrackingHooks()


def get_cost_tracking_hooks() -> CostTrackingHooks:
    return _cost_tracking_hooks

