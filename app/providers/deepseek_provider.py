import logging
import httpx

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from app.providers.base import BaseProvider
from app.providers.http_client import post_with_retry

logger = logging.getLogger("openchawn.provider.deepseek")


class DeepSeekProvider(BaseProvider):
    """DeepSeek — API OpenAI-compatible."""

    def __init__(self) -> None:
        self.api_key = DEEPSEEK_API_KEY
        self.model = DEEPSEEK_MODEL
        self.base_url = DEEPSEEK_BASE_URL.rstrip("/")

    def generate(self, prompt: str, user_id: str = "", system_prompt: str = "") -> str:
        sp = system_prompt or (
            "Tu es OpenChawn. Réponds brièvement. Ne mentionne pas le nom du moteur sous-jacent."
        )
        if not self.api_key:
            return "[ERREUR] DEEPSEEK_API_KEY non configurée."
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
        return bool(self.api_key)
