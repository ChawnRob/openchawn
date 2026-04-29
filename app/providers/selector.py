import logging
from app.providers.base import BaseProvider
from app.providers.ollama_provider import OllamaProvider

logger = logging.getLogger("openchawn.selector")


def select_providers() -> list[tuple[str, BaseProvider]]:
    """MODE OLLAMA-ONLY — aucun fallback, aucun cloud."""
    logger.info("Mode single-provider: ollama")
    return [("ollama", OllamaProvider())]
