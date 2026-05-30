from __future__ import annotations

import os

from app.llm.adapters.http import chat_completions
from app.llm.types import AdapterCompletion
from app.provider_runtime_config import resolve_deepseek_api_key
from app.settings import Settings


def deepseek_model_for_task(task_type: str) -> str:
    t = (task_type or "").strip().lower()
    if t in {"reasoning", "analysis", "premium_tools", "complex"}:
        return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
    return "deepseek-v4-flash"


class DeepSeekAdapter:
    name = "deepseek"

    def is_configured(self, settings: Settings) -> bool:
        _ = settings
        return bool(resolve_deepseek_api_key())

    def complete(
        self,
        *,
        settings: Settings,
        system_prompt: str,
        user_message: str,
        task_type: str = "",
    ) -> AdapterCompletion:
        dkey = resolve_deepseek_api_key()
        if not dkey:
            return AdapterCompletion("", None, "DEEPSEEK_API_KEY_MISSING")
        text, code, err = chat_completions(
            base_url=settings.deepseek_base_url,
            api_key=dkey,
            model=deepseek_model_for_task(task_type),
            system_prompt=system_prompt,
            user_message=user_message,
            log_label="deepseek",
        )
        return AdapterCompletion(text, code, err)
