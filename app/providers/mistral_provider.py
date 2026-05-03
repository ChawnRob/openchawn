import logging
import httpx
from app.providers.base import BaseProvider
from app.providers.http_client import post_with_retry
from app.config import MISTRAL_API_KEY, MISTRAL_MODEL, MISTRAL_BASE_URL

logger = logging.getLogger("openchawn.provider.mistral")


class MistralProvider(BaseProvider):
    """Provider Mistral API cloud — endpoint OpenAI-compatible."""

    def __init__(self):
        self.api_key = MISTRAL_API_KEY
        self.model = MISTRAL_MODEL
        self.base_url = MISTRAL_BASE_URL

    def generate(self, prompt: str, user_id: str = "", system_prompt: str = "") -> str:
        sp = system_prompt or "Tu es OpenChawn. Réponds brièvement. Ne mentionne jamais Mistral, OpenAI ou un autre provider."
        if not self.api_key:
            return "[ERREUR] MISTRAL_API_KEY non configurée."
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
                    "temperature": 0.7,
                },
                timeout=60.0,
                provider_name="mistral",
            )
            return response.json()["choices"][0]["message"]["content"]
        except httpx.ConnectError:
            logger.warning("Mistral API non accessible (ConnectError)")
            return "[ERREUR] Mistral API non accessible."
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            logger.warning(f"Mistral API HTTP {code}")
            if code == 429:
                return "[ERREUR:429] Mistral rate limit épuisé."
            return f"[ERREUR] Mistral API a répondu {code}"
        except (KeyError, IndexError):
            return "[ERREUR] Réponse Mistral inattendue."
        except Exception as e:
            logger.warning(f"Mistral erreur: {e}")
            return f"[ERREUR] {str(e)}"

    def is_available(self) -> bool:
        return bool(self.api_key)
