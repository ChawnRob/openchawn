import re

# Patterns de raisonnement interne à supprimer
_THINK_PATTERNS = [
    re.compile(r"<think>.*?</think>", re.DOTALL),
    re.compile(r"<thinking>.*?</thinking>", re.DOTALL),
    re.compile(r"<reason>.*?</reason>", re.DOTALL),
    re.compile(r"<reasoning>.*?</reasoning>", re.DOTALL),
    re.compile(r"<thought>.*?</thought>", re.DOTALL),
    re.compile(r"<internal>.*?</internal>", re.DOTALL),
    # Tags non fermés (modèle qui ouvre <think> sans fermer)
    re.compile(r"<think>.*", re.DOTALL),
    re.compile(r"<thinking>.*", re.DOTALL),
]


def sanitize_response(text: str) -> str:
    """Supprime tout bloc de raisonnement interne d'une réponse LLM.

    Nettoie les tags <think>, <thinking>, <reason>, <reasoning>,
    <thought>, <internal> et leurs contenus.
    Retourne uniquement la réponse finale utilisateur.
    """
    if not text:
        return text

    cleaned = text
    for pattern in _THINK_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Supprimer les lignes vides résiduelles en début/fin
    cleaned = cleaned.strip()

    # Supprimer les sauts de ligne multiples (max 2 consécutifs)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned
