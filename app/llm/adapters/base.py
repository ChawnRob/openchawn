"""Provider adapter protocol — one implementation per LLM backend."""

from __future__ import annotations

from typing import Protocol

from app.llm.types import AdapterCompletion
from app.settings import Settings


class ProviderAdapter(Protocol):
    @property
    def name(self) -> str: ...

    def is_configured(self, settings: Settings) -> bool: ...

    def complete(
        self,
        *,
        settings: Settings,
        system_prompt: str,
        user_message: str,
        task_type: str = "",
    ) -> AdapterCompletion: ...
