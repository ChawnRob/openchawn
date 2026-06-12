"""
Politique de langue OpenChawn — heuristique locale, sans LLM ni dépendance lourde.

Priorité:
1) traduction / langue cible explicite,
2) demande explicite de langue,
3) langue dominante du dernier message,
4) fallback français si indétectable.
"""

from __future__ import annotations

import os
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
    "und": "non déterminée",
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
    # Phrases du type « Traduis « merci » en espagnol » (mot intermédiaire quelconque).
    (r"\btraduis\s+.+\ben\s+espagnol\b", "es"),
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
        "explique",
        "expliquez",
        "décris",
        "decris",
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
        "and",
        "name",
        "my",
        "me",
        "or",
        "we",
        "it",
        "she",
        "her",
        "him",
        "his",
        "its",
        "get",
        "got",
    }
)


def normalize_language_code(code: str | None) -> str:
    """Normalise un code ou alias utilisateur ; entrée inconnue → ``und`` (pas de forçage français)."""
    if not code:
        return "und"
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
    return "und"


def _is_language_meta_complaint(text: str) -> bool:
    """Questions sur la langue de réponse — pas une demande explicite de changer de langue."""
    lower = (text or "").strip().lower()
    if not lower:
        return False
    meta_patterns = (
        r"\bpourquoi\b.+\b(en anglais|anglais|in english|english)\b",
        r"\bwhy\b.+\b(in english|english|en anglais)\b",
        r"\bpourquoi\b.+\b(repond|reply|parle|speak|ecri)\w*",
    )
    return any(re.search(p, lower, flags=re.IGNORECASE) for p in meta_patterns)


def _explicit_language_override(text: str) -> str | None:
    """Si plusieurs formulations explicites, la **dernière** occurrence dans le texte l'emporte."""
    if _is_language_meta_complaint(text):
        return None
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
    if _is_language_meta_complaint(raw):
        return None
    target = _explicit_translation_target(raw)
    if target:
        return {"kind": "translation_target", "language": normalize_language_code(target)}
    explicit = _explicit_language_override(raw)
    if explicit:
        return {"kind": "explicit_language", "language": normalize_language_code(explicit)}
    return None


def detect_surface_language(text: str) -> str:
    """
    Langue probable du *fond* du message (scores lexicaux), **sans** appliquer
    les motifs « réponds en X » / « traduis en X » ni la priorité translation/explicit.

    ASCII ambigu ou sans signal → ``en`` (pas de défaut français implicite).
    """
    raw = (text or "").strip()
    if not raw:
        return "und"

    norm = raw.replace("\u2019", " ").replace("'", " ").replace("`", " ")
    lower = norm.lower()
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
    if en_score > 0 and fr_score > 0:
        return "en"
    if en_score == 0 and fr_score == 0:
        if re.search(r"[àâäéèêëïîôùûç]", raw):
            return "fr"
        return "en"
    if en_score > 0:
        return "en"
    return "fr"


def detect_user_language(text: str) -> str:
    """
    Détection pour la compat historique : explicites / traduction **avant**
    analyse de surface (`detect_surface_language`).
    """
    raw = (text or "").strip()
    if not raw:
        return "und"

    req = detect_explicit_language_request(raw)
    if req:
        return normalize_language_code(req.get("language"))

    return detect_surface_language(raw)


def derive_response_language_trace(message: str) -> dict[str, str]:
    """
    Métadonnées de politique de langue sans appel mémoire / LLM.

    ``response_language_mode``:
      - translate / explicit — contrainte détectée dans le texte utilisateur ;
      - auto — aucune contrainte : ``final_language`` suit la surface (``und`` → ``en``) ;
      - fixed — léger override ops via ``OPENCHAWN_CHAT_FIXED_LANGUAGE`` (code ISO courte).
    """
    raw = (message or "").strip()
    surf = detect_surface_language(raw)
    surf_n = normalize_language_code(surf)
    surf_final_auto = surf_n if surf_n != "und" else "en"

    fixed_raw = (os.getenv("OPENCHAWN_CHAT_FIXED_LANGUAGE") or "").strip()
    if fixed_raw:
        return {
            "response_language_mode": "fixed",
            "detected_language": surf_n,
            "final_language": normalize_language_code(fixed_raw),
            "language_source": "OPENCHAWN_CHAT_FIXED_LANGUAGE",
        }

    req = detect_explicit_language_request(raw)
    if req and req.get("kind") == "translation_target":
        return {
            "response_language_mode": "translate",
            "detected_language": surf_n,
            "final_language": normalize_language_code(str(req.get("language") or "und")),
            "language_source": "translation_target",
        }
    if req and req.get("kind") == "explicit_language":
        return {
            "response_language_mode": "explicit",
            "detected_language": surf_n,
            "final_language": normalize_language_code(str(req.get("language") or "und")),
            "language_source": "explicit_language_request",
        }
    return {
        "response_language_mode": "auto",
        "detected_language": surf_n,
        "final_language": normalize_language_code(surf_final_auto),
        "language_source": "auto_detect_surface",
    }


_ENGLISH_NAME: Final[dict[str, str]] = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese",
    "de": "German",
    "it": "Italian",
    "fr": "French",
    "und": "the user's language (prefer English if ambiguous ASCII/latin text)",
}


def build_language_instruction(user_message: str) -> str:
    """
    Consigne injectée en tête du message utilisateur (hors bloc mémoire).

    Règle critique: pour une cible anglaise, **toute** la consigne est en anglais — un bloc
    entièrement en français amorçait les modèles vers des réponses en français malgré
    « langue détectée: anglais » en fin de phrase.
    """
    req = detect_explicit_language_request(user_message)
    code = normalize_language_code((req or {}).get("language") or detect_user_language(user_message))
    label_fr = _LABELS.get(code) or _LABELS.get("und", "non déterminée")
    label_en = _ENGLISH_NAME.get(code, "the matching language")

    if code == "fr":
        if req and req.get("kind") == "translation_target":
            return (
                "Réponds obligatoirement dans la langue du dernier message utilisateur. "
                "Exception prioritaire: ici il s'agit d'une demande de traduction, "
                f"donc la sortie principale doit être en {label_fr}."
            )
        if req and req.get("kind") == "explicit_language":
            return (
                "Réponds obligatoirement dans la langue du dernier message utilisateur. "
                "Exception prioritaire: ici l'utilisateur demande explicitement une langue, "
                f"donc réponds en {label_fr}."
            )
        return (
            "Réponds obligatoirement dans la langue du dernier message utilisateur. "
            f"Langue détectée : {label_fr}."
        )

    if code == "en":
        if req and req.get("kind") == "translation_target":
            return (
                "Translation / target language: English. "
                "Produce the main deliverable in English only, even if other parts of the message are not in English."
            )
        if req and req.get("kind") == "explicit_language":
            return (
                "The user explicitly requested English. "
                "Write your entire reply in English. Do not answer in French."
            )
        return (
            "OUTPUT LANGUAGE: English. Write your complete reply in English only. "
            "Do not answer in French. Do not claim you can only express yourself in French."
        )

    if code == "und":
        return (
            "OUTPUT LANGUAGE: Match the user's latest message. "
            "If the message is clearly English, reply entirely in English and not in French. "
            "If unclear, prefer English for short ASCII/Latin text without French-specific accents."
        )

    if code in ("es", "pt", "de", "it"):
        if req and req.get("kind") == "translation_target":
            return (
                f"Translation / target language: {label_en}. "
                f"Produce the main output in {label_en} only."
            )
        if req and req.get("kind") == "explicit_language":
            return (
                f"The user explicitly requested {label_en}. "
                f"Write your entire reply in {label_en}. Do not answer in French."
            )
        return (
            f"OUTPUT LANGUAGE: {label_en}. Write your complete reply in {label_en} only. "
            "Do not default to French."
        )

    return (
        f"OUTPUT LANGUAGE: {label_en}. Follow the user's language. "
        "Do not default to French unless the user's message is clearly French."
    )
