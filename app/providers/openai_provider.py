import logging
import httpx
from app.providers.base import BaseProvider
from app.providers.http_client import post_with_retry
from app.config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL

logger = logging.getLogger("openchawn.provider.openai")


class OpenAIProvider(BaseProvider):
    """Fallback API compatible OpenAI."""

    def __init__(self):
        self.api_key = OPENAI_API_KEY
        self.model = OPENAI_MODEL
        self.base_url = OPENAI_BASE_URL

    def generate(self, prompt: str, user_id: str = "", system_prompt: str = "") -> str:
        sp = system_prompt or "Tu es OpenChawn. Réponds brièvement. Ne mentionne jamais Mistral, OpenAI ou un autre provider."
        if not self.api_key:
            return "[ERREUR] OPENAI_API_KEY non configurée."
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
                },
                timeout=60.0,
                provider_name="openai",
            )
            return response.json()["choices"][0]["message"]["content"]
        except httpx.ConnectError:
            logger.warning("OpenAI API non accessible (ConnectError)")
            return "[ERREUR] API OpenAI non accessible."
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            logger.warning(f"OpenAI HTTP {code}")
            if code == 429:
                return "[ERREUR:429] OpenAI rate limit épuisé."
            return f"[ERREUR] API OpenAI a répondu {code}"
        except (KeyError, IndexError):
            return "[ERREUR] Réponse OpenAI inattendue."
        except Exception as e:
            logger.warning(f"OpenAI erreur: {e}")
            return f"[ERREUR] {str(e)}"

    def is_available(self) -> bool:
        return bool(self.api_key)
