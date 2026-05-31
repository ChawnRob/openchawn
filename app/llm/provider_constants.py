"""Canonical LLM provider order — shared by ProviderManager and adapters."""

from __future__ import annotations

# Ordre canonique après DEFAULT_PROVIDER (uniquement si clé configurée).
FIXED_ORDER: tuple[str, ...] = (
    "deepseek",
    "kimi",
    "openai",
    "infomaniak",
    "openrouter",
)
