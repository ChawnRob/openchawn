"""
Configuration runtime providers : lecture centralisée des variables d'environnement
(aliases inclus). Aucune valeur de secret exportée hors process.
"""
from __future__ import annotations

import os
from typing import Iterable

RUNTIME_SOURCE = "app.provider_runtime_config"

# Ordre de précédence pour l'API DeepSeek native (sans OpenRouter).
DEEPSEEK_API_KEY_ENV_ALIASES: tuple[str, ...] = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_KEY",
    "DEEPSEEK_TOKEN",
    "OPENCHAWN_DEEPSEEK_API_KEY",
)

OPENROUTER_KEY_ENV_ALIASES: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "OPEN_ROUTER_API_KEY",
)

OPENAI_KEY_ENV_ALIASES: tuple[str, ...] = ("OPENAI_API_KEY",)

ENV_NAMES_PROVIDER_RUNTIME_DIAGNOSTIC: tuple[str, ...] = (
    *DEEPSEEK_API_KEY_ENV_ALIASES,
    "DEEPSEEK_MODEL",
    "DEEPSEEK_BASE_URL",
    "DEFAULT_PROVIDER",
    *OPENROUTER_KEY_ENV_ALIASES,
    "OPENROUTER_MODEL",
    "OPENROUTER_BASE_URL",
    *OPENAI_KEY_ENV_ALIASES,
)


def _first_nonempty(names: Iterable[str]) -> tuple[str, str]:
    for k in names:
        v = (os.getenv(k) or "").strip()
        if v:
            return k, v
    return "", ""


def resolve_deepseek_api_key() -> str:
    _, val = _first_nonempty(DEEPSEEK_API_KEY_ENV_ALIASES)
    return val


def resolve_openrouter_api_key() -> str:
    _, val = _first_nonempty(OPENROUTER_KEY_ENV_ALIASES)
    return val


def deepseek_model_configured() -> bool:
    m = (os.getenv("DEEPSEEK_MODEL") or "").strip()
    if m:
        return True
    from app.settings import get_settings

    return bool((get_settings().deepseek_model or "").strip())


def deepseek_base_url_configured() -> bool:
    if (os.getenv("DEEPSEEK_BASE_URL") or "").strip():
        return True
    from app.settings import get_settings

    return bool((get_settings().deepseek_base_url or "").strip())


def get_provider_runtime_config() -> dict[str, object]:
    """
    Vue diagnostic pour /health/provider-runtime : booléens et chemins de code,
    jamais de valeurs de clés.
    """
    from app.provider_manager import get_provider_manager
    from app.settings import get_settings

    s = get_settings()
    pm = get_provider_manager()
    ds_key = resolve_deepseek_api_key()
    or_key = resolve_openrouter_api_key()
    oa_key = (s.openai_api_key or "").strip()

    return {
        "selected_provider": pm.active_provider() or "",
        "provider_manager_path": "app.provider_manager:ProviderManager|app.llm.gateway:generate_response",
        "deepseek_key_present": bool(ds_key),
        "openrouter_key_present": bool(or_key),
        "openai_key_present": bool(oa_key),
        "deepseek_model_present": deepseek_model_configured(),
        "base_url_present": bool(deepseek_base_url_configured() or (s.openrouter_base_url or "").strip()),
        "env_names_checked": list(ENV_NAMES_PROVIDER_RUNTIME_DIAGNOSTIC),
        "runtime_config_source": RUNTIME_SOURCE,
    }
