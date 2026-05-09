"""
Runtime neutralization of forced-French instructions in LLM prompts and memory context.

Shared with initial_rules line filtering (single source of truth for substrings).
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("openchawn.language_guard")

# Accent-insensitive match: compare using _normalize_for_match() on both haystack and these tokens.
FORCED_FRENCH_LINE_SUBSTRINGS: tuple[str, ...] = (
    "uniquement en francais",
    "repondre uniquement en francais",
    "reponds uniquement en francais",
    "toujours repondre en francais",
    "assistant francais",
    "je ne peux m'exprimer qu'en francais",
    "ne peux m'exprimer qu'en francais",
    "parle uniquement en francais",
    "mes regles actuelles m'imposent",
    "fidele aux regles strictes",
    "regles strictes",
    "/etc/openchawn/initial_rules.json",
    # Prototype historiques (harmonisés en minuscules sans accents — cf. _normalize_for_match sur la ligne).
    "reponds en francais, avec precision, calme et structure",
    "tu parles en francais",
    "ne melange jamais les langues",
    "reponds en francais clair",
    "repondre en francais clair",
    "je ne parle qu'en francais",
    "comme mes regles l'exigent",
    "formule-la en francais",
)

NEUTRAL_LANGUAGE_REPLACEMENT_LINE = (
    "Answer in the dominant language of the latest user message, "
    "except explicit translation or explicit language requests."
)

# Détection réponse modèle (politique langue violée) — accent-insensitive via _normalize_for_match
RESPONSE_FORCED_FRENCH_SUBSTRINGS: tuple[str, ...] = (
    "je ne peux m'exprimer qu'en francais",
    "ne peux m'exprimer qu'en francais",
    "uniquement en francais",
    "repondre uniquement en francais",
    "reponds uniquement en francais",
    "repondrai uniquement en francais",
    "toujours repondre en francais",
    "assistant francais",
    "desole, je ne peux",
    "regles strictes",
    "je ne parle qu'en francais",
    "comme mes regles l'exigent",
    "formule-la en francais",
    "tu parles en francais",
    "ne melange jamais les langues",
)


def assistant_reply_violates_english_user_expectation(text: str | None) -> bool:
    """Réponses indésirables quand l'utilisateur écrit en anglais (excuses / contrainte français uniquement)."""
    if not text or not str(text).strip():
        return False
    low = _normalize_for_match(str(text))
    return any(pat in low for pat in RESPONSE_FORCED_FRENCH_SUBSTRINGS)


def _normalize_for_match(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").replace("’", "'").replace("`", "'")
    nk = unicodedata.normalize("NFD", s)
    stripped = "".join(c for c in nk if unicodedata.category(c) != "Mn")
    return stripped.lower()


def line_contains_forced_french_pattern(line: str) -> bool:
    low = _normalize_for_match(line)
    return any(pat in low for pat in FORCED_FRENCH_LINE_SUBSTRINGS)


def prompt_contains_forced_french(text: str | None) -> bool:
    if not text or not str(text).strip():
        return False
    low = _normalize_for_match(str(text))
    return any(pat in low for pat in FORCED_FRENCH_LINE_SUBSTRINGS)


def strip_forced_french_from_text(text: str) -> tuple[str, bool]:
    """
    Drop lines that match forced-French runtime rules (accent-insensitive).
    Returns (cleaned_text, did_remove).
    """
    raw = text or ""
    if not raw.strip():
        return raw, False
    removed = False
    out_lines: list[str] = []
    for line in raw.splitlines():
        if line_contains_forced_french_pattern(line):
            removed = True
            continue
        out_lines.append(line)
    out = "\n".join(out_lines).strip()
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, removed


def sanitize_provider_prompts(system_prompt: str, user_message: str) -> tuple[str, str, bool]:
    """
    Sanitize prompts just before provider dispatch.
    Appends a single neutral language line to the user message if anything was stripped.
    """
    sp, r1 = strip_forced_french_from_text(system_prompt)
    um, r2 = strip_forced_french_from_text(user_message)
    removed = r1 or r2
    if removed:
        logger.warning("forced_french_runtime_removed=true (provider prompt sanitized)")
        um = f"{um}\n\n{NEUTRAL_LANGUAGE_REPLACEMENT_LINE}".strip()
    return sp, um, removed


def memory_entry_requires_forced_french_deprecation(entry: dict) -> bool:
    md = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    if md.get("forced_french_runtime_rule_removed"):
        return False
    parts = [
        str(entry.get("summary", "")),
        str(entry.get("user_message", "")),
        str(entry.get("assistant_response", "")),
    ]
    return prompt_contains_forced_french("\n".join(parts))


def skip_memory_entry_for_context_injection(entry: dict) -> bool:
    md = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    if md.get("forced_french_runtime_rule_removed"):
        return True
    return memory_entry_requires_forced_french_deprecation(entry)
