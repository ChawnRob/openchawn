"""
Providers LLM : Groq (texte rapide), DeepSeek, Kimi, Mistral, OpenAI (opt-in).

Ordre texte : local > groq > kimi/deepseek/mistral > premium (openai/openrouter) si autorisé.
Pas d'Ollama par défaut. Image analyse / génération : modules séparés (pas Groq).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.provider_runtime_config import (
    DEEPSEEK_API_KEY_ENV_ALIASES,
    OPENROUTER_KEY_ENV_ALIASES,
    resolve_deepseek_api_key,
)
from app.routing import build_intelligent_order, provider_capabilities
from app.routing.intelligent_router import RouterDecision
from app.settings import Settings, get_settings
from app.text_provider_policy import (
    CANONICAL_TEXT_PROVIDER_ORDER,
    is_text_provider_allowed,
    parse_text_provider_order,
    preferred_text_provider,
)


def reset_provider_manager_singleton() -> None:
    """Tests / reload : casser le singleton en mémoire."""
    global _manager
    _manager = None


def _required_env_for_provider(name: str) -> str:
    n = _normalize_provider_name(name)
    if n == "groq":
        return "GROQ_API_KEY"
    if n == "deepseek":
        return "|".join(DEEPSEEK_API_KEY_ENV_ALIASES)
    if n == "kimi":
        return "KIMI_API_KEY"
    if n == "mistral":
        return "MISTRAL_API_KEY"
    if n == "openai":
        return "OPENAI_API_KEY"
    if n == "infomaniak":
        return "INFOMANIAK_API_KEY"
    if n == "openrouter":
        return "|".join(OPENROUTER_KEY_ENV_ALIASES)
    if n == "local":
        return "OLLAMA_ENABLED"
    return ""


# Ordre canonique texte (local > groq > kimi/deepseek/mistral > premium).
FIXED_ORDER: tuple[str, ...] = CANONICAL_TEXT_PROVIDER_ORDER


def _normalize_provider_name(name: str) -> str:
    return (name or "").strip().lower()


@dataclass
class ProviderManager:
    settings: Settings

    def _has(self, name: str) -> bool:
        """Présence d'une clé ou backend configuré pour ce provider."""
        n = _normalize_provider_name(name)
        s = self.settings
        if n == "groq":
            return bool((s.groq_api_key or "").strip())
        if n == "deepseek":
            return bool(resolve_deepseek_api_key())
        if n == "kimi":
            return bool((s.kimi_api_key or "").strip())
        if n == "mistral":
            return bool((s.mistral_api_key or "").strip())
        if n == "openrouter":
            return bool((s.openrouter_api_key or "").strip())
        if n == "openai":
            return bool(s.openai_enabled and (s.openai_api_key or "").strip())
        if n == "anthropic":
            return bool(s.anthropic_enabled)
        if n == "infomaniak":
            return bool((s.infomaniak_api_key or "").strip())
        if n == "local":
            return bool(s.ollama_enabled and ((s.ollama_base_url or s.ollama_url or "").strip()))
        return False

    def _resolution_order(self) -> list[str]:
        """DEFAULT_TEXT_PROVIDER en tête puis TEXT_PROVIDER_ORDER (clés + policy)."""
        pref = preferred_text_provider(self.settings)
        canonical = parse_text_provider_order(self.settings.text_provider_order)
        ordered: list[str] = []

        if pref in canonical and self._has(pref) and is_text_provider_allowed(pref, self.settings):
            ordered.append(pref)

        for n in canonical:
            if n == pref:
                continue
            if self._has(n) and is_text_provider_allowed(n, self.settings):
                ordered.append(n)

        return ordered

    def resolution_order(self) -> list[str]:
        return list(self._resolution_order())

    def intelligent_order(
        self,
        *,
        system_prompt: str,
        user_message: str,
        provider_hint: str = "",
    ) -> list[str]:
        configured = self._resolution_order()
        if not configured:
            return []
        decision = self.intelligent_decision(
            system_prompt=system_prompt,
            user_message=user_message,
            provider_hint=provider_hint,
        )
        if not decision.ordered_providers:
            return configured
        # Re-filter scored order through policy (premium gate, openai disabled, etc.)
        allowed = set(configured)
        filtered = [p for p in decision.ordered_providers if p in allowed]
        return filtered or configured

    def intelligent_decision(
        self,
        *,
        system_prompt: str,
        user_message: str,
        provider_hint: str = "",
    ) -> RouterDecision:
        configured = self._resolution_order()
        return build_intelligent_order(
            configured_providers=configured,
            default_provider=preferred_text_provider(self.settings),
            system_prompt=system_prompt,
            user_message=user_message,
            provider_hint=provider_hint,
        )

    def configured_providers(self) -> list[str]:
        return [n for n in parse_text_provider_order(self.settings.text_provider_order) if self._has(n) and is_text_provider_allowed(n, self.settings)]

    def active_provider(self) -> str:
        ro = self.resolution_order()
        return ro[0] if ro else ""

    def missing_keys(self) -> list[str]:
        """Diagnostic Railway (sans secrets)."""
        pref = preferred_text_provider(self.settings)
        missing: list[str] = []

        req = _required_env_for_provider(pref)
        if req and not self._has(pref):
            missing.append(req)

        if self.resolution_order():
            return missing

        if not missing:
            return [
                "Configurer au moins une clé texte : GROQ_API_KEY (recommandée), "
                "puis optionnellement KIMI_API_KEY, DEEPSEEK_API_KEY, MISTRAL_API_KEY."
            ]

        return missing

    def production_safe(self) -> bool:
        s = self.settings
        if not s.is_production:
            return True
        if not s.secret_key or s.secret_key == "dev-secret-change-me-in-production":
            return False
        raw_urls = (
            os.environ.get("OLLAMA_URL", ""),
            os.environ.get("OLLAMA_BASE_URL", ""),
            (s.ollama_url or ""),
            (s.ollama_base_url or ""),
        )
        for u in raw_urls:
            ul = (u or "").lower()
            if "localhost:11434" in ul or "127.0.0.1:11434" in ul:
                return False
        return True

    def capabilities_snapshot(self) -> dict[str, dict[str, object]]:
        return {
            key: dict(cap)
            for key, cap in provider_capabilities.items()
        }


_manager: ProviderManager | None = None


def get_provider_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager(get_settings())
    return _manager


PROVIDER_PRIORITY: tuple[str, ...] = FIXED_ORDER
