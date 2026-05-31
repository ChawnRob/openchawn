from __future__ import annotations

from app.llm.adapters.registry import dispatch_adapter
from app.llm.generation_service import GenerationService, get_generation_service
from app.llm.provider_constants import FIXED_ORDER

# Re-export for tests patching gateway._dispatch
from app.llm.adapters.deepseek import deepseek_model_for_task  # noqa: F401

__all__ = [
    "FIXED_ORDER",
    "GenerationService",
    "generate_response",
    "get_generation_service",
    "dispatch_adapter",
    "_dispatch",
]


def _dispatch(
    name: str,
    s,
    system_prompt: str,
    user_message: str,
    task_type: str = "",
) -> tuple[str, int | None, str | None]:
    """Thin wrapper — delegates to adapter registry (backward compatible)."""
    return dispatch_adapter(name, s, system_prompt, user_message, task_type=task_type)


def generate_response(
    *,
    system_prompt: str,
    user_message: str,
    provider_hint: str = "",
) -> dict[str, str | bool | int | None]:
    """
    Chaîne **explicite uniquement parmi providers configurés** :
    ordre intelligent DeepSeek/Kimi/OpenAI/Infomaniak (avec OpenRouter en compat).
    """
    result = get_generation_service().generate(
        system_prompt=system_prompt,
        user_message=user_message,
        provider_hint=provider_hint,
    )
    return result.to_dict()
