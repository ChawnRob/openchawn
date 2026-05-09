import logging
import os

import httpx

from app.provider_runtime_config import resolve_deepseek_api_key
from app.settings import _deepseek_base_normalize

from app.providers.base import BaseProvider
from app.providers.http_client import post_with_retry

logger = logging.getLogger("openchawn.provider.deepseek")

_DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com"


class DeepSeekProvider(BaseProvider):
    """DeepSeek — client compatible OpenAI (clé/modèle via os.environ Railway)."""

    def __init__(self) -> None:
        self.api_key = resolve_deepseek_api_key()
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
        raw_base = os.getenv("DEEPSEEK_BASE_URL") or _DEEPSEEK_DEFAULT_BASE
        self.base_url = _deepseek_base_normalize(raw_base).rstrip("/")

    def generate(self, prompt: str, user_id: str = "", system_prompt: str = "") -> str:
        sp = system_prompt or (
            "Tu es OpenChawn. Réponds brièvement. Ne mentionne pas le nom du moteur sous-jacent."
        )
        if not self.api_key:
            return "[ERREUR] DEEPSEEK_API_KEY non configurée."
        try:
            response = post_with_retry(
                url=f"{self.base_url.rstrip('/')}/chat/completions",
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
                provider_name="deepseek",
            )
            return response.json()["choices"][0]["message"]["content"]
        except httpx.ConnectError:
            logger.warning("DeepSeek non accessible (ConnectError)")
            return "[ERREUR] API DeepSeek non accessible."
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            logger.warning(f"DeepSeek HTTP {code}")
            if code == 429:
                return "[ERREUR:429] DeepSeek rate limit épuisé."
            return f"[ERREUR] DeepSeek a répondu {code}"
        except (KeyError, IndexError):
            return "[ERREUR] Réponse DeepSeek inattendue."
        except Exception as e:
            logger.warning(f"DeepSeek erreur: {e}")
            return f"[ERREUR] {str(e)}"

    def is_available(self) -> bool:
        return bool(resolve_deepseek_api_key())
