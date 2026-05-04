from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Interface commune pour tous les providers LLM."""

    @abstractmethod
    def generate(self, prompt: str, user_id: str = "", system_prompt: str = "") -> str:
        """Génère une réponse. system_prompt injecté en role: system."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Vérifie si le provider est accessible."""
        ...
