from __future__ import annotations

from dataclasses import dataclass

from app.routing.fallback_manager import get_fallback_manager
from app.routing.provider_capabilities import provider_capabilities
from app.routing.provider_health_hooks import get_provider_health_hooks
from app.routing.provider_scoring import RouterContext, score_provider


@dataclass(frozen=True)
class RouterDecision:
    primary: str
    ordered_providers: list[str]
    task_type: str
    enterprise_sovereign_mode: bool


def _infer_task_type(message: str) -> str:
    text = (message or "").strip().lower()
    if not text:
        return "simple"
    if any(k in text for k in ("souverain", "sovereign", "rgpd", "compliance", "eu")):
        return "enterprise_sovereign"
    if len(text) > 4000 or any(k in text for k in ("contexte long", "long context", "agentique", "multi-etapes")):
        return "long_context"
    if any(k in text for k in ("raisonne", "analyse", "proof", "step by step", "diagnostic")):
        return "reasoning"
    if any(k in text for k in ("tool", "api", "integration", "automation", "pipeline", "ci")):
        return "premium_tools"
    return "simple"


def _estimate_tokens(system_prompt: str, user_message: str) -> int:
    chars = len(system_prompt or "") + len(user_message or "")
    return max(1, chars // 4)


def build_intelligent_order(
    configured_providers: list[str],
    default_provider: str,
    system_prompt: str,
    user_message: str,
    provider_hint: str = "",
) -> RouterDecision:
    hint = (provider_hint or "").strip().lower()
    enterprise_mode = hint in {"infomaniak", "euria", "souverain", "sovereign"}

    task_type = _infer_task_type(user_message)
    estimated_tokens = _estimate_tokens(system_prompt, user_message)
    prefer_quality = task_type in {"reasoning", "premium_tools", "analysis"}
    ctx = RouterContext(
        task_type=task_type,
        estimated_input_tokens=estimated_tokens,
        prefer_quality=prefer_quality,
        enterprise_sovereign_mode=enterprise_mode or task_type == "enterprise_sovereign",
    )

    health = get_provider_health_hooks()
    fallback = get_fallback_manager()
    candidates: list[tuple[float, str]] = []
    for provider_name in configured_providers:
        for cap in provider_capabilities.values():
            if str(cap.get("provider", "")) != provider_name:
                continue
            health_boost = health.availability_boost(provider_name)
            penalty = fallback.health_penalty(provider_name)
            score = score_provider(cap, ctx, availability_boost=health_boost) - penalty
            candidates.append((score, provider_name))

    if not candidates:
        return RouterDecision(
            primary=(default_provider or "").strip().lower(),
            ordered_providers=[],
            task_type=task_type,
            enterprise_sovereign_mode=ctx.enterprise_sovereign_mode,
        )

    # Keep one best score per provider
    best_by_provider: dict[str, float] = {}
    for score, provider in candidates:
        current = best_by_provider.get(provider)
        if current is None or score > current:
            best_by_provider[provider] = score

    ordered = [
        p for p, _ in sorted(best_by_provider.items(), key=lambda item: item[1], reverse=True)
    ]
    if hint in best_by_provider:
        ordered = [hint] + [p for p in ordered if p != hint]
    elif default_provider in best_by_provider:
        # Keep default near top for stability if score differences are small.
        top = ordered[0] if ordered else default_provider
        if top != default_provider and best_by_provider[top] - best_by_provider[default_provider] < 6.0:
            ordered = [default_provider] + [p for p in ordered if p != default_provider]

    return RouterDecision(
        primary=ordered[0],
        ordered_providers=ordered,
        task_type=task_type,
        enterprise_sovereign_mode=ctx.enterprise_sovereign_mode,
    )

