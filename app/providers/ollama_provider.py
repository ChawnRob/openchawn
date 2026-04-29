import time
import logging
import httpx
from app.providers.base import BaseProvider
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger("openchawn.provider.ollama")


class OllamaProvider(BaseProvider):
    """Provider local via Ollama — endpoint /api/chat."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url
        self.model = model
        self._available: bool | None = None
        self._checked_at: float = 0

    def generate(self, prompt: str, user_id: str = "", system_prompt: str = "") -> str:
        sp = system_prompt or "Tu es un assistant IA."
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": sp},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            # Succès → marquer disponible
            self._available = True
            self._checked_at = time.time()
            return response.json().get("message", {}).get("content", "")
        except httpx.ConnectError:
            self._available = False
            self._checked_at = time.time()
            logger.warning("Ollama non accessible (ConnectError)")
            return "[ERREUR] Ollama non accessible."
        except httpx.HTTPStatusError as e:
            logger.warning(f"Ollama HTTP {e.response.status_code}")
            return f"[ERREUR] Ollama a répondu {e.response.status_code}"
        except Exception as e:
            logger.warning(f"Ollama erreur: {e}")
            return f"[ERREUR] {str(e)}"

    def is_available(self) -> bool:
        """Check avec cache 60s — UN SEUL appel /api/tags par minute max."""
        now = time.time()
        if self._available is not None and (now - self._checked_at) < 60:
            return self._available
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            self._available = r.status_code == 200
        except Exception:
            self._available = False
        self._checked_at = now
        logger.debug(f"Ollama check: available={self._available}")
        return self._available
