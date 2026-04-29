from __future__ import annotations
import os
import httpx
from app.providers.base import BaseProvider


class KimiProvider(BaseProvider):
    """Provider Kimi K2.6 (Moonshot AI) — tier premium OpenChawn."""

    def __init__(self) -> None:
        self.api_key    = os.getenv("KIMI_API_KEY", "").strip()
        self.base_url   = os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
        self.model      = os.getenv("KIMI_MODEL", "kimi-k2-0905-preview")
        self.temperature = float(os.getenv("KIMI_TEMPERATURE", "0.6"))
        self.timeout    = float(os.getenv("KIMI_TIMEOUT", "120"))
        self.max_tokens = int(os.getenv("KIMI_MAX_TOKENS", "2048"))

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
