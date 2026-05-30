from __future__ import annotations

from app.llm.adapters.http import openai_responses
from app.llm.types import AdapterCompletion
from app.settings import Settings


class OpenAIAdapter:
    name = "openai"

    def is_configured(self, settings: Settings) -> bool:
        return bool((settings.openai_api_key or "").strip())

    def complete(
        self,
        *,
        settings: Settings,
        system_prompt: str,
        user_message: str,
        task_type: str = "",
    ) -> AdapterCompletion:
        _ = task_type
        text, code, err = openai_responses(settings, system_prompt, user_message)
        return AdapterCompletion(text, code, err)
