class QEIScorer:
    """
    Quality Evaluation Index — scoring local des réponses.
    Pas de modèle externe, heuristiques simples et extensibles.
    """

    def score(self, prompt: str, response: str) -> dict:
        scores = {
            "length": self._score_length(response),
            "relevance": self._score_relevance(prompt, response),
            "error": self._score_error(response),
        }
        scores["total"] = round(sum(scores.values()) / len(scores), 2)
        return scores

    def _score_length(self, response: str) -> float:
        """Pénalise les réponses trop courtes ou vides."""
        length = len(response.strip())
        if length == 0:
            return 0.0
        if length < 10:
            return 0.3
        if length < 50:
            return 0.6
        return 1.0

    def _score_relevance(self, prompt: str, response: str) -> float:
        """Score basique : mots du prompt présents dans la réponse."""
        prompt_words = set(prompt.lower().split())
        response_lower = response.lower()
        if not prompt_words:
            return 0.5
        matches = sum(1 for w in prompt_words if w in response_lower)
        ratio = matches / len(prompt_words)
        return round(min(ratio * 1.5, 1.0), 2)

    def _score_error(self, response: str) -> float:
        """Détecte les réponses d'erreur."""
        if "[ERREUR]" in response:
            return 0.0
        return 1.0
