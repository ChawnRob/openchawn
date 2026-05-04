"""Clients LLM légers (hors couche providers orchestrateur)."""

from app.llm.gateway import generate_response
from app.llm.moonshot import moonshot_chat_completion

__all__ = ["moonshot_chat_completion", "generate_response"]
