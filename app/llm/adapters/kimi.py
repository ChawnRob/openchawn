from __future__ import annotations

from app.llm.adapters.http import chat_completions
from app.llm.types import AdapterCompletion
from app.settings import Settings


class KimiAdapter:
    name = "kimi"

    def is_configured(self, settings: Settings) -> bool:
        return bool((settings.kimi_api_key or "").strip())

    def complete(
        self,
        *,
        settings: Settings,
        system_prompt: str,
        user_message: str,
        task_type: str = "",
    ) -> AdapterCompletion:
        _ = task_type
        key = (settings.kimi_api_key or "").strip()
        if not key:
            return AdapterCompletion("", None, "KIMI_API_KEY_MISSING")
        base = (settings.kimi_base_url or "").strip().rstrip("/") or "https://api.moonshot.ai/v1"
        model = (settings.kimi_model or "").strip() or "kimi-k2-0905-preview"
        text, code, err = chat_completions(
            base_url=base,
            api_key=key,
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
            log_label="kimi",
        )
        return AdapterCompletion(text, code, err)
