import logging
import httpx
from app.providers.base import BaseProvider
from app.providers.http_client import post_with_retry
from app.config import MINIMAX_API_KEY, MINIMAX_MODEL, MINIMAX_BASE_URL

logger = logging.getLogger("openchawn.provider.minimax")


class MinimaxProvider(BaseProvider):
    """Provider MiniMax officiel (M2.7) — API OpenAI-compatible."""

    def __init__(self):
        self.api_key = MINIMAX_API_KEY
        self.model = MINIMAX_MODEL
        self.base_url = MINIMAX_BASE_URL

    def generate(self, prompt: str, user_id: str = "", system_prompt: str = "") -> str:
        sp = system_prompt or "Tu es OpenChawn. Réponds brièvement. Ne mentionne jamais Mistral, OpenAI ou un autre provider."
        if not self.api_key:
            return "[ERREUR] MINIMAX_API_KEY non configurée."
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
                timeout=120.0,
                provider_name="minimax",
            )
            return response.json()["choices"][0]["message"]["content"]
        except httpx.ConnectError:
            logger.warning("MiniMax non accessible (ConnectError)")
            return "[ERREUR] API MiniMax non accessible."
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            logger.warning(f"MiniMax HTTP {code}")
            if code == 429:
                return "[ERREUR:429] MiniMax rate limit épuisé."
            return f"[ERREUR] MiniMax a répondu {code}"
        except (KeyError, IndexError):
            return "[ERREUR] Réponse MiniMax inattendue."
        except Exception as e:
            logger.warning(f"MiniMax erreur: {e}")
            return f"[ERREUR] {str(e)}"

    def is_available(self) -> bool:
        return bool(self.api_key)
