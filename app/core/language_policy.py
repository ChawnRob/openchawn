"""
Politique de langue OpenChawn — heuristique locale, sans LLM ni dépendance lourde.

Règle produit : répondre dans la langue du dernier message utilisateur
(dominante si mélange ; langue demandée explicitement si formulée).
"""

from __future__ import annotations

import re
from typing import Final

LANGUAGE_POLICY_ENABLED: Final[bool] = True
FALLBACK_LANGUAGE: Final[str] = "fr"
LANGUAGE_POLICY_RULE_PUBLIC: Final[str] = (
    "La réponse suit la langue du dernier message utilisateur "
    "(dominante si mélange FR/EN ; priorité à une demande explicite de langue)."
)

_LABELS: Final[dict[str, str]] = {"fr": "français", "en": "anglais"}

# Paires (regex sur texte lower), langue cible si correspondance.
_EXPLICIT_LANG_PATTERNS: Final[list[tuple[str, str]]] = [
    (r"\banswer\s+in\s+english\b", "en"),
    (r"\breply\s+in\s+english\b", "en"),
    (r"\brespond\s+in\s+english\b", "en"),
    (r"\bwrite\s+in\s+english\b", "en"),
    (r"\bplease\s+use\s+english\b", "en"),
    (r"\bspeak\s+english\b", "en"),
    (r"\bin\s+english\b", "en"),
    (r"\buse\s+english\b", "en"),
    (r"\ben\s+anglais\b", "en"),
    (r"\brépond(?:s|re)?\s+en\s+anglais\b", "en"),
    (r"\breply\s+in\s+french\b", "fr"),
    (r"\banswer\s+in\s+french\b", "fr"),
    (r"\bin\s+french\b", "fr"),
    (r"\ben\s+français\b", "fr"),
    (r"\ben\s+francais\b", "fr"),
    (r"\brépond(?:s|re)?\s+en\s+français\b", "fr"),
    (r"\brépond(?:s|re)?\s+en\s+francais\b", "fr"),
]

_FR_WORDS: Final[frozenset[str]] = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "est",
        "été",
        "être",
        "pas",
        "pour",
        "avec",
        "sans",
        "que",
        "qui",
        "dont",
        "dans",
        "sur",
        "sous",
        "mais",
        "donc",
        "très",
        "plus",
        "moins",
        "aussi",
        "bonjour",
        "salut",
        "merci",
        "vous",
        "nous",
        "leur",
        "ceci",
        "cela",
        "comment",
        "pourquoi",
        "quand",
        "combien",
        "avez",
        "êtes",
        "sommes",
        "faire",
        "fait",
        "voir",
        "bien",
        "mal",
        "oui",
        "non",
        "ici",
        "là",
        "je",
        "tu",
        "il",
        "elle",
        "chez",
        "voici",
        "peut",
        "doit",
        "besoin",
        "votre",
        "notre",
        "ses",
        "son",
        "sa",
        "mes",
        "tes",
    }
)

_EN_WORDS: Final[frozenset[str]] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "how",
        "this",
        "that",
        "these",
        "those",
        "with",
        "without",
        "from",
        "into",
        "about",
        "please",
        "thanks",
        "thank",
        "hello",
        "hi",
        "yes",
        "not",
        "you",
        "your",
        "our",
        "they",
        "them",
        "their",
        "can",
        "must",
        "need",
        "make",
        "just",
        "also",
        "very",
        "more",
        "most",
        "here",
        "there",
    }
)


def normalize_language_code(code: str | None) -> str:
    """Normalise un code ou alias utilisateur vers ``fr`` ou ``en`` (fallback ``fr``)."""
    if not code:
        return FALLBACK_LANGUAGE
    c = str(code).strip().lower().replace("_", "-")
    if c == "en" or c.startswith("en-"):
        return "en"
    if c in ("eng", "english", "anglais"):
        return "en"
    if c == "fr" or c.startswith("fr-"):
        return "fr"
    if c in ("fra", "french", "français", "francais"):
        return "fr"
    return FALLBACK_LANGUAGE


def _explicit_language_override(text: str) -> str | None:
    """Si plusieurs formulations explicites, la **dernière** occurrence dans le texte l'emporte."""
    lower = text.lower()
    best_lang: str | None = None
    best_start = -1
    for pattern, lang in _EXPLICIT_LANG_PATTERNS:
        for m in re.finditer(pattern, lower, flags=re.IGNORECASE):
            if m.start() >= best_start:
                best_start = m.start()
                best_lang = lang
    return best_lang


def detect_user_language(text: str) -> str:
    """
    Détection heuristique ``fr`` / ``en``.

    Priorité aux demandes explicites de langue ; sinon scores lexicaux + accents FR ;
    égalité ou absence de signal → ``FALLBACK_LANGUAGE`` (français).
    """
    raw = (text or "").strip()
    if not raw:
        return FALLBACK_LANGUAGE

    explicit = _explicit_language_override(raw)
    if explicit:
        return normalize_language_code(explicit)

    lower = raw.lower()
    tokens = re.findall(r"[a-zàâäéèêëïîôùûç]+", lower, flags=re.IGNORECASE)
    fr_score = 0
    en_score = 0
    for tok in tokens:
        t = tok.lower()
        if t in _FR_WORDS:
            fr_score += 1
        if t in _EN_WORDS:
            en_score += 1

    fr_score += len(re.findall(r"[àâäéèêëïîôùûç]", raw)) * 2

    if fr_score > en_score:
        return "fr"
    if en_score > fr_score:
        return "en"
    return FALLBACK_LANGUAGE


def build_language_instruction(user_message: str) -> str:
    """
    Consigne injectée dans le message utilisateur final (hors bloc mémoire).

    Format officiel OpenChawn pour le provider.
    """
    code = normalize_language_code(detect_user_language(user_message))
    label = _LABELS.get(code, _LABELS[FALLBACK_LANGUAGE])
    return f"Réponds dans la même langue que le dernier message utilisateur : {label}."
