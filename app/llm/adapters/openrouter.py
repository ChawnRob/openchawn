from __future__ import annotations

from app.llm.adapters.http import chat_completions
from app.llm.types import AdapterCompletion
from app.settings import Settings


class OpenRouterAdapter:
    name = "openrouter"

    def is_configured(self, settings: Settings) -> bool:
        return bool((settings.openrouter_api_key or "").strip())

    def complete(
        self,
        *,
        settings: Settings,
        system_prompt: str,
        user_message: str,
        task_type: str = "",
    ) -> AdapterCompletion:
        _ = task_type
        text, code, err = chat_completions(
            base_url=settings.openrouter_base_url,
            api_key=(settings.openrouter_api_key or "").strip(),
            model=settings.openrouter_model,
            system_prompt=system_prompt,
            user_message=user_message,
            log_label="openrouter",
        )
        return AdapterCompletion(text, code, err)
