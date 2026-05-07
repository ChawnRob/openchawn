from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouterContext:
    task_type: str
    estimated_input_tokens: int
    prefer_quality: bool = False
    enterprise_sovereign_mode: bool = False


def _cost_score(cap: dict[str, object]) -> float:
    # Lower cost is better: normalize into 0..100
    raw = float(cap.get("estimated_cost_per_1k_tokens_usd", 0.4))
    return max(0.0, 100.0 - (raw * 160.0))


def _context_fit_score(cap: dict[str, object], estimated_input_tokens: int) -> float:
    if estimated_input_tokens <= 0:
        return 80.0
    max_ctx = float(cap.get("max_context_tokens", 32000))
    ratio = min(1.0, max_ctx / float(estimated_input_tokens))
    return 40.0 + (ratio * 60.0)


def score_provider(cap: dict[str, object], ctx: RouterContext, availability_boost: float = 0.0) -> float:
    if ctx.enterprise_sovereign_mode and not bool(cap.get("enterprise_sovereign_ready", False)):
        return -1.0

    quality_weight = 0.45 if ctx.prefer_quality else 0.30
    cost_weight = 0.25 if ctx.prefer_quality else 0.40
    context_weight = 0.20
    priority_weight = 0.10

    quality = float(cap.get("reasoning_score", 65))
    cost = _cost_score(cap)
    context_fit = _context_fit_score(cap, ctx.estimated_input_tokens)
    priority = float(cap.get("priority", 50))

    score = (
        quality * quality_weight
        + cost * cost_weight
        + context_fit * context_weight
        + priority * priority_weight
        + availability_boost
    )

    task_profiles = [str(x) for x in cap.get("task_profiles", [])]
    if ctx.task_type not in task_profiles:
        score -= 6.0
    return score

