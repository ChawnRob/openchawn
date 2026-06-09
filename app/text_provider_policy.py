"""
Text LLM provider policy — order, premium gating, analysis/generation separation.

Image analysis and image generation use dedicated modules; Groq is text-only here.
"""
from __future__ import annotations

from app.settings import Settings, get_settings

SUPPORTED_TEXT_PROVIDERS = frozenset(
    {"local", "groq", "kimi", "deepseek", "mistral", "openai", "infomaniak", "openrouter", "anthropic"}
)

PREMIUM_TEXT_PROVIDERS = frozenset({"openai", "anthropic", "openrouter"})

CANONICAL_TEXT_PROVIDER_ORDER: tuple[str, ...] = (
    "local",
    "groq",
    "kimi",
    "deepseek",
    "mistral",
    "openai",
    "infomaniak",
    "openrouter",
)


def parse_text_provider_order(raw: str | None = None) -> list[str]:
    source = (raw or get_settings().text_provider_order or "").strip()
    if not source:
        source = ",".join(CANONICAL_TEXT_PROVIDER_ORDER)
    seen: set[str] = set()
    order: list[str] = []
    for part in source.split(","):
        pid = part.strip().lower()
        if not pid or pid in seen:
            continue
        if pid in SUPPORTED_TEXT_PROVIDERS:
            order.append(pid)
            seen.add(pid)
    return order or list(CANONICAL_TEXT_PROVIDER_ORDER)


def is_text_provider_allowed(name: str, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    n = (name or "").strip().lower()
    if n not in SUPPORTED_TEXT_PROVIDERS:
        return False
    if n == "openai" and not s.openai_enabled:
        return False
    if n == "anthropic" and not s.anthropic_enabled:
        return False
    if n in PREMIUM_TEXT_PROVIDERS and not s.allow_premium_models:
        return False
    if n == "local":
        return bool(s.ollama_enabled and ((s.ollama_base_url or s.ollama_url or "").strip()))
    return True


def preferred_text_provider(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    pref = (s.default_text_provider or s.default_provider or "groq").strip().lower()
    return pref if pref in SUPPORTED_TEXT_PROVIDERS else "groq"
