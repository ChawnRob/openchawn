from __future__ import annotations

from app.llm.adapters.http import chat_completions
from app.llm.types import AdapterCompletion
from app.settings import Settings


class InfomaniakAdapter:
    name = "infomaniak"

    def is_configured(self, settings: Settings) -> bool:
        return bool(
            (settings.infomaniak_api_key or "").strip()
            and (settings.infomaniak_model or "").strip()
            and (settings.infomaniak_base_url or "").strip()
        )

    def complete(
        self,
        *,
        settings: Settings,
        system_prompt: str,
        user_message: str,
        task_type: str = "",
    ) -> AdapterCompletion:
        _ = task_type
        if not (settings.infomaniak_api_key or "").strip():
            return AdapterCompletion("", None, "INFOMANIAK_API_KEY_MISSING")
        if not (settings.infomaniak_model or "").strip():
            return AdapterCompletion("", None, "INFOMANIAK_MODEL_MISSING")
        if not (settings.infomaniak_base_url or "").strip():
            return AdapterCompletion("", None, "INFOMANIAK_BASE_URL_MISSING")
        text, code, err = chat_completions(
            base_url=(settings.infomaniak_base_url or "").strip().rstrip("/"),
            api_key=(settings.infomaniak_api_key or "").strip(),
            model=(settings.infomaniak_model or "").strip(),
            system_prompt=system_prompt,
            user_message=user_message,
            log_label="infomaniak",
        )
        return AdapterCompletion(text, code, err)
