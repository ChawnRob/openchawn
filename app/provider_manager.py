"""
Détection des providers LLM disponibles et ordre de résolution (chat gateway).

Providers supportés : OpenRouter, OpenAI, DeepSeek, Kimi, Infomaniak (à venir), Ollama (hors prod).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

from app.settings import Settings, get_settings

# Ordre après DEFAULT_PROVIDER / MODEL_PROVIDER (si clés présentes)
PROVIDER_PRIORITY: tuple[str, ...] = (
    "openrouter",
    "openai",
    "deepseek",
    "kimi",
    "infomaniak",
    "ollama",
)


def _key_var_for(name: str) -> str:
    return {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
        "infomaniak": "INFOMANIAK_API_KEY",
        "ollama": "OLLAMA_ENABLED",
    }.get(name, "")


@dataclass
class ProviderManager:
    settings: Settings
    _memo_order: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._memo_order = list(self._resolution_order())

    def _has(self, name: str) -> bool:
        s = self.settings
        if name == "openrouter":
            return bool(s.openrouter_api_key)
        if name == "openai":
            return bool(s.openai_api_key)
        if name == "deepseek":
            return bool(s.deepseek_api_key)
        if name == "kimi":
            return bool(s.kimi_effective_key)
        if name == "infomaniak":
            return bool(s.infomaniak_api_key) and bool(s.infomaniak_base_url) and bool(
                s.infomaniak_model
            )
        if name == "ollama":
            if not s.ollama_enabled:
                return False
            base = (s.ollama_base_url or s.ollama_url or "").strip()
            return bool(base)
        return False

    def _resolution_order(self) -> Iterable[str]:
        """
        Ordre : DEFAULT_PROVIDER (si clé) → MODEL_PROVIDER legacy (si clé) → liste standard.
        """
        s = self.settings
        seen: set[str] = set()
        ordered: list[str] = []

        def add(name: str) -> None:
            n = (name or "").strip().lower()
            if not n or n in seen:
                return
            if self._has(n):
                ordered.append(n)
                seen.add(n)

        add(s.default_provider)
        add(s.model_provider)

        for p in PROVIDER_PRIORITY:
            if p not in seen:
                ordered.append(p)
                seen.add(p)

        return ordered

    def resolution_order(self) -> list[str]:
        return list(self._memo_order)

    def available_providers(self) -> list[str]:
        return [p for p in self._memo_order if self._has(p)]

    def active_provider(self) -> str:
        """Premier provider réellement utilisable dans l’ordre résolu."""
        for p in self._memo_order:
            if self._has(p):
                return p
        return ""

    def missing_required_keys(self) -> list[str]:
        """
        Si DEFAULT_PROVIDER est fixé mais indisponible (clé manquante),
        retourne les variables attendues.
        """
        s = self.settings
        d = (s.default_provider or "").strip().lower()
        if not d:
            return []
        if self._has(d):
            return []
        valid = set(PROVIDER_PRIORITY)
        if d not in valid:
            return [f"DEFAULT_PROVIDER={d!r} n'est pas reconnu (providers: {', '.join(PROVIDER_PRIORITY)})."]
        kv = _key_var_for(d)
        if d == "ollama":
            if not s.ollama_enabled:
                return ["OLLAMA_ENABLED=true (interdit si OPENCHAWN_ENV=production) et OLLAMA_URL"]
            return ["OLLAMA_URL ou OLLAMA_BASE_URL"]
        if d == "infomaniak":
            missing = []
            if not s.infomaniak_api_key:
                missing.append("INFOMANIAK_API_KEY")
            if not s.infomaniak_base_url:
                missing.append("INFOMANIAK_BASE_URL")
            if not s.infomaniak_model:
                missing.append("INFOMANIAK_MODEL")
            return missing or ["INFOMANIAK_* incomplet"]
        return [kv] if kv else []

    def production_safe(self) -> bool:
        s = self.settings
        if not s.is_production:
            return True
        if (
            not s.secret_key
            or s.secret_key == "dev-secret-change-me-in-production"
        ):
            return False
        if s.ollama_enabled:
            return False
        if not s.ollama_enabled:
            raw_urls = [
                os.environ.get("OLLAMA_URL", ""),
                os.environ.get("OLLAMA_BASE_URL", ""),
            ]
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
