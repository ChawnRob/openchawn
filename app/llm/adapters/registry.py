from __future__ import annotations

from app.llm.adapters.deepseek import DeepSeekAdapter
from app.llm.adapters.infomaniak import InfomaniakAdapter
from app.llm.adapters.kimi import KimiAdapter
from app.llm.adapters.openai import OpenAIAdapter
from app.llm.adapters.openrouter import OpenRouterAdapter
from app.llm.types import AdapterCompletion
from app.provider_manager import FIXED_ORDER
from app.settings import Settings

_ADAPTERS: dict[str, object] = {
    "deepseek": DeepSeekAdapter(),
    "kimi": KimiAdapter(),
    "openai": OpenAIAdapter(),
    "infomaniak": InfomaniakAdapter(),
    "openrouter": OpenRouterAdapter(),
}


def get_adapter(name: str):
    return _ADAPTERS.get((name or "").strip().lower())


def get_all_adapters():
    return [(n, _ADAPTERS[n]) for n in FIXED_ORDER if n in _ADAPTERS]


def dispatch_adapter(
    name: str,
    settings: Settings,
    system_prompt: str,
    user_message: str,
    task_type: str = "",
) -> tuple[str, int | None, str | None]:
    """Backward-compatible dispatch shape for gateway._dispatch and tests."""
    adapter = get_adapter(name)
    if adapter is None:
        return "", None, "UNKNOWN_PROVIDER"
    completion: AdapterCompletion = adapter.complete(
        settings=settings,
        system_prompt=system_prompt,
        user_message=user_message,
        task_type=task_type,
    )
    return completion.text, completion.status_code, completion.error
