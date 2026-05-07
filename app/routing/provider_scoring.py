from __future__ import annotations

from dataclasses import dataclass

from app.routing.provider_capabilities import ProviderCapability


@dataclass(frozen=True)
class RouterContext:
    task_type: str
    estimated_input_tokens: int
    prefer_quality: bool = False
    enterprise_sovereign_mode: bool = False


def _cost_score(cap: ProviderCapability) -> float:
    # Lower cost is better: normalize into 0..100
    return max(0.0, 100.0 - (cap.estimated_cost_per_1k_tokens_usd * 160.0))


def _context_fit_score(cap: ProviderCapability, estimated_input_tokens: int) -> float:
    if estimated_input_tokens <= 0:
        return 80.0
    ratio = min(1.0, cap.max_context_tokens / float(estimated_input_tokens))
    return 40.0 + (ratio * 60.0)


def score_provider(cap: ProviderCapability, ctx: RouterContext, availability_boost: float = 0.0) -> float:
    if ctx.enterprise_sovereign_mode and not cap.enterprise_sovereign_ready:
        return -1.0

    quality_weight = 0.45 if ctx.prefer_quality else 0.30
    cost_weight = 0.25 if ctx.prefer_quality else 0.40
    context_weight = 0.20
    priority_weight = 0.10

    quality = float(cap.reasoning_score)
    cost = _cost_score(cap)
    context_fit = _context_fit_score(cap, ctx.estimated_input_tokens)
    priority = float(cap.priority)

    score = (
        quality * quality_weight
        + cost * cost_weight
        + context_fit * context_weight
        + priority * priority_weight
        + availability_boost
    )

    if ctx.task_type not in cap.task_profiles:
        score -= 6.0
    return score

