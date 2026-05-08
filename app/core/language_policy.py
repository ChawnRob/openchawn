"""
Politique de langue OpenChawn — heuristique locale, sans LLM ni dépendance lourde.

Priorité:
1) traduction / langue cible explicite,
2) demande explicite de langue,
3) langue dominante du dernier message,
4) fallback français si indétectable.
"""

from __future__ import annotations

import re
from typing import Final

LANGUAGE_POLICY_ENABLED: Final[bool] = True
FALLBACK_LANGUAGE: Final[str] = "fr"
LANGUAGE_POLICY_RULE_PUBLIC: Final[str] = (
    "La réponse suit une priorité stricte: traduction/langue cible explicite, puis demande explicite "
    "de langue, puis langue dominante du dernier message utilisateur, puis fallback français."
)

_LABELS: Final[dict[str, str]] = {
    "fr": "français",
    "en": "anglais",
    "es": "espagnol",
    "pt": "portugais",
    "de": "allemand",
    "it": "italien",
}

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
    (r"\banswer\s+in\s+spanish\b", "es"),
    (r"\breply\s+in\s+spanish\b", "es"),
    (r"\bin\s+spanish\b", "es"),
    (r"\ben\s+espagnol\b", "es"),
    (r"\ben\s+español\b", "es"),
    (r"\banswer\s+in\s+portuguese\b", "pt"),
    (r"\breply\s+in\s+portuguese\b", "pt"),
    (r"\bin\s+portuguese\b", "pt"),
    (r"\ben\s+portugais\b", "pt"),
]

_TRANSLATION_TARGET_PATTERNS: Final[list[tuple[str, str]]] = [
    (r"\btraduis(?:-moi)?(?:\s+ce\s+texte)?\s+en\s+anglais\b", "en"),
    (r"\btraduis(?:-moi)?(?:\s+ce\s+texte)?\s+en\s+français\b", "fr"),
    (r"\btraduis(?:-moi)?(?:\s+ce\s+texte)?\s+en\s+francais\b", "fr"),
    (r"\btraduis(?:-moi)?(?:\s+ce\s+texte)?\s+en\s+espagnol\b", "es"),
    (r"\btraduis(?:-moi)?(?:\s+ce\s+texte)?\s+en\s+español\b", "es"),
    (r"\btraduis(?:-moi)?(?:\s+ce\s+texte)?\s+en\s+portugais\b", "pt"),
    (r"\btranslate(?:\s+this|\s+it|\s+the\s+text)?\s+to\s+english\b", "en"),
    (r"\btranslate(?:\s+this|\s+it|\s+the\s+text)?\s+to\s+french\b", "fr"),
    (r"\btranslate(?:\s+this|\s+it|\s+the\s+text)?\s+to\s+spanish\b", "es"),
    (r"\btranslate(?:\s+this|\s+it|\s+the\s+text)?\s+to\s+portuguese\b", "pt"),
    (r"\btranslate(?:\s+this|\s+it|\s+the\s+text)?\s+into\s+english\b", "en"),
    (r"\btranslate(?:\s+this|\s+it|\s+the\s+text)?\s+into\s+french\b", "fr"),
    (r"\btranslate(?:\s+this|\s+it|\s+the\s+text)?\s+into\s+spanish\b", "es"),
    (r"\btranslate(?:\s+this|\s+it|\s+the\s+text)?\s+into\s+portuguese\b", "pt"),
    (r"\bmets?\s+ça\s+en\s+anglais\b", "en"),
    (r"\bmets?\s+ça\s+en\s+français\b", "fr"),
    (r"\bmets?\s+ça\s+en\s+francais\b", "fr"),
    (r"\bmets?\s+ça\s+en\s+espagnol\b", "es"),
    (r"\bmets?\s+ça\s+en\s+español\b", "es"),
    (r"\bmets?\s+ça\s+en\s+portugais\b", "pt"),
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
        "explain",
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
    """Normalise un code ou alias utilisateur (fallback ``fr``)."""
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
    if c == "es" or c.startswith("es-"):
        return "es"
    if c in ("spa", "spanish", "espagnol", "español", "espanol"):
        return "es"
    if c == "pt" or c.startswith("pt-"):
        return "pt"
    if c in ("por", "portuguese", "portugais", "português", "portugues"):
        return "pt"
    if c == "de" or c.startswith("de-") or c in ("ger", "deu", "german", "allemand"):
        return "de"
    if c == "it" or c.startswith("it-") or c in ("ita", "italian", "italien"):
        return "it"
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


def _explicit_translation_target(text: str) -> str | None:
    """Retourne la langue cible d'une demande de traduction (dernière occurrence)."""
    lower = text.lower()
    best_lang: str | None = None
    best_start = -1
    for pattern, lang in _TRANSLATION_TARGET_PATTERNS:
        for m in re.finditer(pattern, lower, flags=re.IGNORECASE):
            if m.start() >= best_start:
                best_start = m.start()
                best_lang = lang
    return best_lang


def detect_explicit_language_request(text: str) -> dict[str, str] | None:
    """
    Détecte une contrainte explicite de langue.

    Renvoie:
    - ``{"kind":"translation_target","language":"<code>"}`` si demande de traduction vers cible,
    - ``{"kind":"explicit_language","language":"<code>"}`` si demande explicite de langue,
    - ``None`` sinon.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    target = _explicit_translation_target(raw)
    if target:
        return {"kind": "translation_target", "language": normalize_language_code(target)}
    explicit = _explicit_language_override(raw)
    if explicit:
        return {"kind": "explicit_language", "language": normalize_language_code(explicit)}
    return None


def detect_user_language(text: str) -> str:
    """
    Détection heuristique ``fr`` / ``en``.

    Priorité aux demandes explicites (traduction incluse) ; sinon scores lexicaux + accents FR ;
    égalité ou absence de signal → ``FALLBACK_LANGUAGE`` (français).
    """
    raw = (text or "").strip()
    if not raw:
        return FALLBACK_LANGUAGE

    req = detect_explicit_language_request(raw)
    if req:
        return normalize_language_code(req.get("language"))

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
    req = detect_explicit_language_request(user_message)
    code = normalize_language_code((req or {}).get("language") or detect_user_language(user_message))
    label = _LABELS.get(code, _LABELS[FALLBACK_LANGUAGE])
    if req and req.get("kind") == "translation_target":
        return (
            "Réponds obligatoirement dans la langue du dernier message utilisateur. "
            "Exception prioritaire: ici il s'agit d'une demande de traduction, "
            f"donc la sortie principale doit être en {label}."
        )
    if req and req.get("kind") == "explicit_language":
        return (
            "Réponds obligatoirement dans la langue du dernier message utilisateur. "
            "Exception prioritaire: ici l'utilisateur demande explicitement une langue, "
            f"donc réponds en {label}."
        )
    return (
        "Réponds obligatoirement dans la langue du dernier message utilisateur. "
        f"Langue détectée: {label}."
    )
