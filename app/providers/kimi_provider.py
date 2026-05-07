from __future__ import annotations

import httpx

from app.config import (
    KIMI_API_KEY,
    KIMI_BASE_URL,
    KIMI_MODEL,
    KIMI_MAX_TOKENS,
    KIMI_TEMPERATURE,
    KIMI_TIMEOUT,
)
from app.providers.base import BaseProvider


class KimiProvider(BaseProvider):
    """Kimi — API Moonshot/OpenAI-compatible (optionnel si KIMI_API_KEY vide)."""

    def __init__(self) -> None:
        self.api_key = (KIMI_API_KEY or "").strip()
        self.base_url = (KIMI_BASE_URL or "https://api.moonshot.ai/v1").strip().rstrip("/")
        self.model = ((KIMI_MODEL or "").strip()) or "kimi-k2-0905-preview"
        try:
            self.temperature = float(KIMI_TEMPERATURE)
        except (TypeError, ValueError):
            self.temperature = 0.6
        try:
            self.timeout = float(KIMI_TIMEOUT)
        except (TypeError, ValueError):
            self.timeout = 120.0
        try:
            self.max_tokens = int(KIMI_MAX_TOKENS)
        except (TypeError, ValueError):
            self.max_tokens = 2048

    # ─── Interface BaseProvider ────────────────────────────────────────

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        prompt: str,
        user_id: str = "",
        system_prompt: str = "",
    ) -> str:
        if not self.is_available():
            return "[ERREUR] KIMI_API_KEY non défini."

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if user_id:
            payload["user"] = user_id

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text[:200] if e.response is not None else ""
            return f"[ERREUR] Kimi HTTP {e.response.status_code}: {body}"
        except httpx.RequestError as e:
            return f"[ERREUR] Kimi réseau: {e}"
        except Exception as e:
            return f"[ERREUR] Kimi inattendu: {e}"

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            return f"[ERREUR] Kimi réponse malformée: {str(data)[:200]}"
