"""
Providers LLM : DeepSeek (par défaut), Kimi optionnel, OpenRouter, OpenAI.
Pas d’Ollama, pas de chaînage localhost:11434.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

from app.settings import Settings, get_settings

# Ordre canonique après DEFAULT_PROVIDER (uniquement si clé configurée).
FIXED_ORDER: tuple[str, ...] = (
    "deepseek",
    "kimi",
    "openrouter",
    "openai",
)


def _normalize_provider_name(name: str) -> str:
    return (name or "").strip().lower()


def _key_var_env(name: str) -> str:
    return {
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
    }.get(name, "")


@dataclass
class ProviderManager:
    settings: Settings
    _memo_order: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._memo_order = list(self._resolution_order())

    def _has(self, name: str) -> bool:
        """Présence d’une clé configurée pour ce provider."""
        n = _normalize_provider_name(name)
        s = self.settings
        if n == "deepseek":
            return bool((s.deepseek_api_key or "").strip())
        if n == "kimi":
            return bool((s.kimi_api_key or "").strip())
        if n == "openrouter":
            return bool((s.openrouter_api_key or "").strip())
        if n == "openai":
            return bool((s.openai_api_key or "").strip())
        return False

    def _resolution_order(self) -> Iterable[str]:
        """DEFAULT_PROVIDER avec clé en tête puis FIXED_ORDER avec clés présentes uniquement."""
        s = self.settings
        pref = _normalize_provider_name(s.default_provider)
        ordered: list[str] = []

        if pref in FIXED_ORDER and self._has(pref):
            ordered.append(pref)

        for n in FIXED_ORDER:
            if n != pref and self._has(n):
                ordered.append(n)

        return ordered

    def resolution_order(self) -> list[str]:
        return list(self._memo_order)

    def configured_providers(self) -> list[str]:
        """Providers avec au moins une clé configurée (ordre de secours prévu)."""
        return [
            n for n in FIXED_ORDER if self._has(n)
        ]

    def active_provider(self) -> str:
        """Premier utilisé après résolution (= premier avec clé, default en premier si valide)."""
        if self._memo_order:
            return self._memo_order[0]
        return ""

    def missing_keys(self) -> list[str]:
        """Variables Railway pertinentes encore absentes (diagnostic, sans valeurs sensibles)."""
        s = self.settings
        pref = _normalize_provider_name(s.default_provider)
        missing: list[str] = []

        if pref == "deepseek" and not (s.deepseek_api_key or "").strip():
            missing.append("DEEPSEEK_API_KEY")

        if self._memo_order:
            return missing

        if not missing:
            return [
                "Configurer au moins une clé : DEEPSEEK_API_KEY "
                "(recommandée), puis optionnellement KIMI_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY."
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


_manager: ProviderManager | None = None


def get_provider_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager(get_settings())
    return _manager


# Legacy export pour références dans le code
PROVIDER_PRIORITY: tuple[str, ...] = FIXED_ORDER
