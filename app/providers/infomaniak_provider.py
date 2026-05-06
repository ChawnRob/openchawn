"""
Infomaniak (LLM Swiss hosting) — endpoint généralement compatible OpenAI /chat/completions.
Variables : INFOMANIAK_API_KEY, INFOMANIAK_BASE_URL, INFOMANIAK_MODEL
"""
from __future__ import annotations

import logging

import httpx

from app.config import (
    INFOMANIAK_API_KEY,
    INFOMANIAK_BASE_URL,
    INFOMANIAK_MODEL,
)
from app.providers.base import BaseProvider
from app.providers.http_client import post_with_retry

logger = logging.getLogger("openchawn.provider.infomaniak")


class InfomaniakProvider(BaseProvider):
    def __init__(self) -> None:
        self.api_key = (INFOMANIAK_API_KEY or "").strip()
        self.base_url = (INFOMANIAK_BASE_URL or "").strip().rstrip("/")
        self.model = (INFOMANIAK_MODEL or "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def generate(self, prompt: str, user_id: str = "", system_prompt: str = "") -> str:
        sp = system_prompt or (
            "Tu es OpenChawn. Réponds brièvement. Ne mentionne pas le nom du moteur sous-jacent."
        )
        if not self.is_available():
            return "[ERREUR] Infomaniak : renseignez INFOMANIAK_API_KEY, INFOMANIAK_BASE_URL et INFOMANIAK_MODEL."
        try:
            response = post_with_retry(
                url=f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json_data={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": sp},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=120.0,
                provider_name="infomaniak",
            )
            return response.json()["choices"][0]["message"]["content"]
        except httpx.ConnectError:
            logger.warning("Infomaniak non accessible (ConnectError)")
            return "[ERREUR] API Infomaniak non accessible."
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            logger.warning(f"Infomaniak HTTP {code}")
            return f"[ERREUR] Infomaniak a répondu {code}"
        except (KeyError, IndexError):
            return "[ERREUR] Réponse Infomaniak inattendue."
        except Exception as e:
            logger.warning(f"Infomaniak erreur: {e}")
            return f"[ERREUR] {str(e)}"
