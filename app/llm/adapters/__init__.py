"""Chat LLM provider adapters (Phase 1 — extracted from gateway._dispatch)."""

from app.llm.adapters.base import ProviderAdapter
from app.llm.adapters.deepseek import DeepSeekAdapter
from app.llm.adapters.infomaniak import InfomaniakAdapter
from app.llm.adapters.kimi import KimiAdapter
from app.llm.adapters.openai import OpenAIAdapter
from app.llm.adapters.openrouter import OpenRouterAdapter
from app.llm.adapters.registry import dispatch_adapter, get_adapter, get_all_adapters
from app.provider_manager import FIXED_ORDER

__all__ = [
    "ProviderAdapter",
    "DeepSeekAdapter",
    "KimiAdapter",
    "OpenAIAdapter",
    "InfomaniakAdapter",
    "OpenRouterAdapter",
    "FIXED_ORDER",
    "get_adapter",
    "get_all_adapters",
    "dispatch_adapter",
]
