"""LLM generation orchestration — provider loop extracted from gateway (Phase 1)."""

from __future__ import annotations

import logging

from app.core.runtime_language_guard import prompt_contains_forced_french, sanitize_provider_prompts
from app.llm.adapters.registry import dispatch_adapter
from app.llm.types import ProviderResult
from app.provider_manager import get_provider_manager
from app.provider_runtime_config import resolve_deepseek_api_key
from app.routing import (
    get_cost_tracking_hooks,
    get_fallback_manager,
    get_provider_health_hooks,
)
from app.routing.provider_capabilities import provider_capabilities
from app.settings import get_settings

logger = logging.getLogger("openchawn.gateway")


def _normalize_pref(x: str) -> str:
    return (x or "").strip().lower()


def _estimate_cost(provider: str, text: str) -> tuple[int, float]:
    tokens = max(1, len(text or "") // 4)
    cap = next(
        (x for x in provider_capabilities.values() if str(x.get("provider", "")) == provider),
        None,
    )
    if not cap:
        return tokens, 0.0
    estimated = (tokens / 1000.0) * float(cap.get("estimated_cost_per_1k_tokens_usd", 0.0))
    return tokens, estimated


class GenerationService:
    """Executes configured provider chain; selection logic unchanged from V11.7 gateway."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_message: str,
        provider_hint: str = "",
    ) -> ProviderResult:
        pre_ff = prompt_contains_forced_french((system_prompt or "") + "\n" + (user_message or ""))
        system_prompt, user_message, ff_runtime_removed = sanitize_provider_prompts(
            system_prompt or "", user_message or ""
        )
        ff_debug = {
            "prompt_contains_forced_french_before_sanitize": bool(pre_ff),
            "forced_french_runtime_removed": bool(ff_runtime_removed),
        }

        s = get_settings()
        pm = get_provider_manager()

        if (
            _normalize_pref(s.default_provider) == "deepseek"
            and not resolve_deepseek_api_key()
            and not pm.resolution_order()
        ):
            return ProviderResult(
                output="",
                provider="none",
                success=False,
                status_code=None,
                error="DeepSeek API key missing",
                **ff_debug,
            )

        decision = pm.intelligent_decision(
            system_prompt=system_prompt,
            user_message=user_message,
            provider_hint=provider_hint,
        )
        seq = decision.ordered_providers
        if not seq:
            seq = pm.resolution_order()

        if not seq:
            return ProviderResult(
                output="",
                provider="none",
                success=False,
                status_code=None,
                error=(
                    "Aucune clé API LLM configurée (DEEPSEEK requis par défaut, "
                    "puis KIMI/OPENAI/INFOMANIAK optionnels)."
                ),
                **ff_debug,
            )

        last_err: str | None = None
        last_code: int | None = None
        fallback = get_fallback_manager()
        health = get_provider_health_hooks()
        cost = get_cost_tracking_hooks()

        for name in seq:
            text, code, err = dispatch_adapter(
                name,
                s,
                system_prompt,
                user_message,
                task_type=decision.task_type,
            )
            if text:
                health.mark_success(name)
                estimated_tokens, estimated_cost = _estimate_cost(
                    name, system_prompt + user_message + text
                )
                cost.track(name, estimated_tokens, estimated_cost)
                return ProviderResult(
                    output=text,
                    provider=name,
                    success=True,
                    status_code=code,
                    error=None,
                    **ff_debug,
                )
            if err:
                health.mark_failure(name)
                fallback.record(name, err)
                last_err = err
                last_code = code
                logger.info(f"provider_fail name={name} err={err}")

        detail = last_err or "Échec de tous les providers configurés."
        return ProviderResult(
            output="",
            provider="none",
            success=False,
            status_code=last_code,
            error=detail,
            **ff_debug,
        )


_default_service: GenerationService | None = None


def get_generation_service() -> GenerationService:
    global _default_service
    if _default_service is None:
        _default_service = GenerationService()
    return _default_service
