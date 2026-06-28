"""
Universal conversational continuity resolver (P1.4).

Tracks short-term entities/topics per chat session and resolves pronoun /
demonstrative references before the LLM is called. No hardcoded domain entities.
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

EntityCategory = Literal[
    "person",
    "organization",
    "company",
    "product",
    "project",
    "repository",
    "place",
    "document",
    "file",
    "image",
    "website",
    "event",
    "concept",
    "object",
    "topic",
]

Confidence = Literal["none", "low", "medium", "high"]

MAX_RECENT_ENTITIES = 12
STATE_TTL_SECONDS = 20 * 60

_ENTITY_CATEGORIES: frozenset[str] = frozenset(
    {
        "person",
        "organization",
        "company",
        "product",
        "project",
        "repository",
        "place",
        "document",
        "file",
        "image",
        "website",
        "event",
        "concept",
        "object",
        "topic",
    }
)

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "as", "is", "was", "are", "were", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must",
        "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them", "my",
        "your", "his", "its", "our", "their", "this", "that", "these", "those", "what", "which",
        "who", "whom", "whose", "when", "where", "why", "how", "all", "each", "every", "both",
        "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same",
        "so", "than", "too", "very", "can", "just", "about", "into", "through", "during", "before",
        "after", "above", "below", "between", "under", "again", "further", "then", "once", "here",
        "there", "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "mais", "donc",
        "or", "ni", "car", "ce", "cet", "cette", "ces", "mon", "ma", "mes", "ton", "ta", "tes",
        "son", "sa", "ses", "notre", "nos", "votre", "vos", "leur", "leurs", "je", "tu", "il",
        "elle", "on", "nous", "vous", "ils", "elles", "me", "te", "se", "lui", "en", "y", "qui",
        "que", "quoi", "dont", "où", "comment", "pourquoi", "quand", "est", "sont", "été", "etre",
        "être", "avoir", "faire", "dire", "aller", "voir", "savoir", "pouvoir", "vouloir", "comme",
        "sur", "dans", "par", "avec", "sans", "plus", "moins", "très", "tres", "bien", "aussi",
        "peux", "peut", "peuvent", "pourrais", "pourrait", "please", "tell", "give", "show",
    }
)

_SELF_REFERENCE_RE = re.compile(
    r"\b(i|me|my|myself|mine|we|us|our|ours|ourselves|"
    r"je|moi|mon|ma|mes|nous|notre|nos)\b",
    re.IGNORECASE,
)

_CAPITALIZED_PHRASE_RE = re.compile(
    r"\b([A-Z][a-z]+(?:['-][A-Za-z]+)?(?:\s+[A-Z][a-z]+(?:['-][A-Za-z]+)?){0,4})\b"
)

_SINGLE_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-z][a-zA-Z0-9]{1,})\b")

_PLACE_PREPOSITION_RE = re.compile(
    r"\b(en|in|à|at|from|de|du|des|sur|near|around)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\b",
    re.IGNORECASE,
)

_CUE_LABEL_RE = re.compile(
    r"\b(?:l['']?)?(?:company|entreprise|soci[eé]t[eé]|organization|organisation|project|projet|product|produit|"
    r"repo(?:sitory)?|d[eé]p[oô]t|brand|marque|startup)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3})",
    re.IGNORECASE,
)

_VERB_COMMANDS = frozenset(
    {
        "summarize", "summarise", "analyze", "analyse", "compare", "describe", "explain", "list",
        "show", "tell", "give", "find", "search", "check", "review", "open", "sync", "create",
        "write", "read", "help", "what", "where", "when", "who", "how", "why", "please",
        "résume", "résumer", "analyse", "analyser", "décris", "decris", "explique", "liste",
        "montre", "donne", "trouve", "cherche", "vérifie", "verifie", "revois",
    }
)

_QUOTED_RE = re.compile(r"""["'«]([^"'»]{2,80})["'»]""")

_URL_RE = re.compile(r"https?://[^\s<>\"']+|www\.[a-z0-9][-a-z0-9.]*\.[a-z]{2,}", re.IGNORECASE)

_REPO_RE = re.compile(r"\b([A-Za-z0-9][-A-Za-z0-9_]*/[A-Za-z0-9][-A-Za-z0-9_.]*)\b")

_PAIR_AND_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3})\s+and\s+"
    r"([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3})\b"
)

_FILE_EXT_RE = re.compile(
    r"\b([\w][\w\s.-]{0,60}\.(?:pdf|docx?|xlsx?|pptx?|csv|txt|md|json|yaml|yml|png|jpe?g|gif|webp))\b",
    re.IGNORECASE,
)

_CATEGORY_CUE_RES: tuple[tuple[EntityCategory, re.Pattern[str]], ...] = (
    (
        "person",
        re.compile(
            r"\b(mr|mrs|ms|dr|prof|m\.|mme|monsieur|madame|founder|fondateur|fondateuse|ceo|"
            r"director|directeur|directrice|engineer|ingénieur|ingénieure|author|auteur|autrice)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "company",
        re.compile(
            r"\b(company|entreprise|soci[eé]t[eé]|corporation|corp|firm|startup|marque|brand)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "organization",
        re.compile(r"\b(organization|organisation|institute|institut|agency|agence|ngo|association)\b", re.IGNORECASE),
    ),
    (
        "product",
        re.compile(r"\b(product|produit|platform|plateforme|service|app|application|tool|outil)\b", re.IGNORECASE),
    ),
    (
        "project",
        re.compile(r"\b(project|projet|initiative|program|programme|roadmap)\b", re.IGNORECASE),
    ),
    (
        "repository",
        re.compile(r"\b(repo(?:sitory)?|d[eé]p[oô]t|github|gitlab|bitbucket)\b", re.IGNORECASE),
    ),
    (
        "place",
        re.compile(r"\b(city|ville|country|pays|region|r[eé]gion|office|bureau|headquarters|si[eè]ge)\b", re.IGNORECASE),
    ),
    (
        "document",
        re.compile(r"\b(document|doc|report|rapport|paper|article|whitepaper|spec|specification)\b", re.IGNORECASE),
    ),
    (
        "file",
        re.compile(r"\b(file|fichier|attachment|pi[eè]ce jointe|upload|uploaded)\b", re.IGNORECASE),
    ),
    (
        "image",
        re.compile(r"\b(image|photo|picture|screenshot|capture|selfie)\b", re.IGNORECASE),
    ),
    (
        "website",
        re.compile(r"\b(website|site web|site|homepage|page|url|link|lien)\b", re.IGNORECASE),
    ),
    (
        "event",
        re.compile(r"\b(event|[eé]v[eé]nement|conference|conf[eé]rence|meeting|r[eé]union|launch|lancement)\b", re.IGNORECASE),
    ),
)

_REFERENCE_PATTERNS: tuple[tuple[str, re.Pattern[str], dict[str, Any]], ...] = (
    (
        "ordinal_second",
        re.compile(r"\b(the second|le second|la seconde|le deuxi[eè]me|la deuxi[eè]me|2(?:nd|e))\b", re.IGNORECASE),
        {"ordinal": 2},
    ),
    (
        "ordinal_first",
        re.compile(r"\b(the first|le premier|la premi[eè]re|1(?:st|er|re))\b", re.IGNORECASE),
        {"ordinal": 1},
    ),
    (
        "former",
        re.compile(r"\b(the former|le pr[eé]c[eé]dent|la pr[eé]c[e9]dente|the previous one)\b", re.IGNORECASE),
        {"ordinal": -2},
    ),
    (
        "latter",
        re.compile(r"\b(the latter|le suivant|la suivante|the next one)\b", re.IGNORECASE),
        {"ordinal": -1},
    ),
    (
        "demonstrative_company",
        re.compile(
            r"\b(this|that|the)\s+(company|startup|firm|business)|"
            r"\b(cette|ce|cette)\s+(entreprise|soci[eé]t[eé]|startup)\b",
            re.IGNORECASE,
        ),
        {"categories": ("company", "organization")},
    ),
    (
        "demonstrative_project",
        re.compile(r"\b(this|that|the)\s+project\b|\b(ce|cette)\s+projet\b", re.IGNORECASE),
        {"categories": ("project",)},
    ),
    (
        "demonstrative_repo",
        re.compile(r"\b(this|that|the)\s+repo(?:sitory)?\b|\b(ce|cette)\s+d[eé]p[oô]t\b", re.IGNORECASE),
        {"categories": ("repository",)},
    ),
    (
        "demonstrative_product",
        re.compile(r"\b(this|that|the)\s+product\b|\b(ce|cette)\s+produit\b", re.IGNORECASE),
        {"categories": ("product",)},
    ),
    (
        "demonstrative_place",
        re.compile(r"\b(this|that|the)\s+(city|place|country)\b|\b(cette|ce)\s+(ville|pays|lieu)\b", re.IGNORECASE),
        {"categories": ("place",)},
    ),
    (
        "demonstrative_document",
        re.compile(r"\b(this|that|the)\s+(document|file|report)\b|\b(ce|cette)\s+(document|fichier|rapport)\b", re.IGNORECASE),
        {"categories": ("document", "file")},
    ),
    (
        "pronoun_masc",
        re.compile(r"\b(he|him|his|il|lui|celui-ci|celui)\b", re.IGNORECASE),
        {"categories": ("person",), "gender": "masc"},
    ),
    (
        "pronoun_fem",
        re.compile(r"\b(she|her|hers|elle|celle-ci|celle)\b", re.IGNORECASE),
        {"categories": ("person",), "gender": "fem"},
    ),
    (
        "pronoun_plural",
        re.compile(r"\b(they|them|their|ils|elles|ceux-ci|ceux|celles)\b", re.IGNORECASE),
        {"categories": ("person", "organization", "company", "product")},
    ),
    (
        "pronoun_neutral",
        re.compile(r"\b(it|its|ça|cela|this|that|those|these)\b", re.IGNORECASE),
        {"categories": ("product", "project", "repository", "document", "file", "image", "concept", "object", "topic", "company", "organization")},
    ),
    (
        "topic_step",
        re.compile(r"\b(next step|prochaine [eé]tape|what(?:'s| is) next|la suite)\b", re.IGNORECASE),
        {"categories": ("project", "topic", "concept")},
    ),
)

_IMAGE_REFERENCE_RE = re.compile(
    r"\b(this|that|it|the)\s+(detail|image|photo|picture)|"
    r"\b(cette|ce|ça|cela)\s+(image|photo|d[eé]tail)|"
    r"\banalyse[- ]?(this|it|the)?\s*(detail|image|photo)?\b|"
    r"\banaly[sz]e\s+(this|it|the)\s+(detail|image|photo)\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _is_stopword(token: str) -> bool:
    return _normalize(token) in _STOPWORDS


@dataclass
class TrackedEntity:
    text: str
    category: EntityCategory
    turn_index: int
    mention_order: int
    is_user_self: bool = False
    gender: str = ""
    source: str = "message"

    def label(self) -> str:
        return f"{self.text} ({self.category})"


@dataclass
class ConversationState:
    session_key: str
    entities: list[TrackedEntity] = field(default_factory=list)
    active_topic: str = ""
    active_category: EntityCategory = "topic"
    turn_count: int = 0
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


@dataclass(frozen=True)
class ContinuityResolution:
    confidence: Confidence
    has_reference: bool
    resolved_entity: TrackedEntity | None = None
    candidates: tuple[TrackedEntity, ...] = ()
    clarification: str = ""
    context_block: str = ""
    effective_message: str = ""
    memory_query: str = ""
    active_topic: str = ""

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "has_reference": self.has_reference,
            "resolved_entity": self.resolved_entity.label() if self.resolved_entity else None,
            "candidate_count": len(self.candidates),
            "clarification": bool(self.clarification),
            "active_topic": self.active_topic or None,
        }


_lock = threading.Lock()
_states: dict[str, ConversationState] = {}


def clear_conversation_states() -> None:
    with _lock:
        _states.clear()


def _purge_expired(now: float | None = None) -> None:
    ts = now if now is not None else time.time()
    expired = [k for k, st in _states.items() if ts - st.updated_at > STATE_TTL_SECONDS]
    for k in expired:
        _states.pop(k, None)


def _get_state(session_key: str) -> ConversationState:
    _purge_expired()
    key = (session_key or "").strip()
    if not key:
        key = "__anonymous__"
    with _lock:
        st = _states.get(key)
        if st is None:
            st = ConversationState(session_key=key)
            _states[key] = st
        return st


def _window_text(message: str, start: int, end: int, *, radius: int = 48) -> str:
    lo = max(0, start - radius)
    hi = min(len(message), end + radius)
    return message[lo:hi]


def _infer_category(text: str, window: str) -> EntityCategory:
    w = _normalize(window)
    for cat, pattern in _CATEGORY_CUE_RES:
        if pattern.search(w):
            return cat
    if _URL_RE.search(text):
        return "website"
    if _REPO_RE.fullmatch(text.strip()):
        return "repository"
    if _FILE_EXT_RE.search(text):
        low = text.lower()
        if any(low.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return "image"
        return "document"
    if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$", text.strip()):
        return "person"
    if re.match(r"^[A-Z][A-Za-z0-9][-A-Za-z0-9]*$", text.strip()):
        return "organization"
    return "topic"


def extract_entities(
    message: str,
    *,
    turn_index: int,
    mention_offset: int = 0,
    image_label: str = "",
) -> list[TrackedEntity]:
    """Generic entity extraction from a user message."""
    raw = (message or "").strip()
    if not raw and not image_label:
        return []

    found: list[TrackedEntity] = []
    seen: set[str] = set()
    order = mention_offset

    def _add(text: str, start: int, end: int, *, category: EntityCategory | None = None, source: str = "message") -> None:
        nonlocal order
        label = re.sub(r"\s+", " ", (text or "").strip())
        if len(label) < 2:
            return
        key = _normalize(label)
        if key in seen or _is_stopword(label):
            return
        if len(label.split()) == 1 and label[0].islower():
            return
        seen.add(key)
        order += 1
        cat = category or _infer_category(label, _window_text(raw, start, end))
        found.append(
            TrackedEntity(
                text=label,
                category=cat,
                turn_index=turn_index,
                mention_order=order,
                is_user_self=False,
                source=source,
            )
        )

    for m in _URL_RE.finditer(raw):
        _add(m.group(0).rstrip(".,;:!?)"), m.start(), m.end(), category="website")

    for m in _REPO_RE.finditer(raw):
        token = m.group(1)
        if "/" in token and not token.startswith("http"):
            _add(token, m.start(), m.end(), category="repository")

    for m in _FILE_EXT_RE.finditer(raw):
        _add(re.sub(r"\s+", " ", m.group(1).strip()), m.start(), m.end())

    for m in _PAIR_AND_RE.finditer(raw):
        _add(m.group(1), m.start(1), m.end(1))
        _add(m.group(2), m.start(2), m.end(2))

    for m in _QUOTED_RE.finditer(raw):
        _add(m.group(1), m.start(), m.end())

    for m in _CUE_LABEL_RE.finditer(raw):
        _add(m.group(1), m.start(1), m.end(1))

    for m in _PLACE_PREPOSITION_RE.finditer(raw):
        _add(m.group(2), m.start(2), m.end(2), category="place")

    for m in _CAPITALIZED_PHRASE_RE.finditer(raw):
        phrase = m.group(1).strip()
        words = phrase.split()
        if all(_is_stopword(w) for w in words):
            continue
        if words and all(len(w) <= 3 and w.isupper() for w in words):
            continue
        if _normalize(words[0]) in _VERB_COMMANDS:
            continue
        _add(phrase, m.start(), m.end())

    for m in _SINGLE_PROPER_NOUN_RE.finditer(raw):
        token = m.group(1)
        if _is_stopword(token) or _normalize(token) in _VERB_COMMANDS:
            continue
        if token in {e.text for e in found}:
            continue
        if any(token in e.text for e in found):
            continue
        _add(token, m.start(), m.end())

    if image_label:
        order += 1
        found.append(
            TrackedEntity(
                text=image_label,
                category="image",
                turn_index=turn_index,
                mention_order=order,
                source="image",
            )
        )

    return found


def _merge_entities(state: ConversationState, new_entities: list[TrackedEntity]) -> None:
    if not new_entities:
        return
    combined = list(state.entities) + list(new_entities)
    dedup: dict[str, TrackedEntity] = {}
    for ent in combined:
        key = f"{_normalize(ent.text)}::{ent.category}"
        prev = dedup.get(key)
        if prev is None or ent.turn_index >= prev.turn_index:
            dedup[key] = ent
    ordered = sorted(dedup.values(), key=lambda e: (e.turn_index, e.mention_order))
    state.entities = ordered[-MAX_RECENT_ENTITIES:]
    if new_entities:
        latest = new_entities[-1]
        state.active_topic = latest.text
        state.active_category = latest.category


def _detect_references(message: str) -> list[tuple[str, re.Pattern[str], dict[str, Any]]]:
    hits: list[tuple[str, re.Pattern[str], dict[str, Any]]] = []
    for name, pattern, meta in _REFERENCE_PATTERNS:
        if pattern.search(message):
            hits.append((name, pattern, meta))
    if _IMAGE_REFERENCE_RE.search(message):
        hits.append(("image_reference", _IMAGE_REFERENCE_RE, {"categories": ("image",)}))
    return hits


def _filter_candidates(
    entities: list[TrackedEntity],
    *,
    categories: tuple[str, ...] | None = None,
    exclude_user_self: bool = True,
) -> list[TrackedEntity]:
    out: list[TrackedEntity] = []
    for ent in reversed(entities):
        if exclude_user_self and ent.is_user_self:
            continue
        if categories and ent.category not in categories:
            continue
        out.append(ent)
    out.reverse()
    return out


def _pick_ordinal(candidates: list[TrackedEntity], ordinal: int) -> list[TrackedEntity]:
    if not candidates:
        return []
    if ordinal == -1:
        return [candidates[-1]] if candidates else []
    if ordinal == -2:
        return [candidates[-2]] if len(candidates) >= 2 else []
    idx = ordinal - 1
    if 0 <= idx < len(candidates):
        return [candidates[idx]]
    return []


def _build_clarification(candidates: list[TrackedEntity], *, language: str = "en") -> str:
    labels = [c.label() for c in candidates[:4]]
    joined = "; ".join(labels)
    if language == "fr":
        return (
            "Je ne suis pas certain de ce à quoi vous faites référence. "
            f"Voulez-vous parler de : {joined} ?"
        )
    return (
        "I'm not sure what you're referring to. "
        f"Do you mean: {joined}?"
    )


def _build_context_block(
    *,
    confidence: Confidence,
    resolved: TrackedEntity | None,
    candidates: list[TrackedEntity],
    active_topic: str,
    active_category: str,
) -> str:
    lines = ["── CONVERSATION CONTINUITY (short-term session state; prefer over long-term memory) ──"]
    if active_topic:
        lines.append(f"active_topic: {active_topic} ({active_category})")
    if resolved and confidence == "high":
        lines.append(f"resolved_referent: {resolved.label()}")
        lines.append(
            "Instruction: The user's latest message refers to the resolved referent above. "
            "Answer about that subject; do not switch to unrelated long-term memory or the user's identity "
            "unless they explicitly refer to themselves."
        )
    elif candidates and confidence == "medium":
        opts = ", ".join(c.label() for c in candidates[:4])
        lines.append(f"possible_referents: {opts}")
        lines.append(
            "Instruction: The user's message contains an ambiguous reference. "
            "Prefer the most recent matching referent from this conversation. "
            "If still unclear, ask a brief clarification."
        )
    else:
        recent = ", ".join(e.label() for e in candidates[-4:]) if candidates else "(none)"
        lines.append(f"recent_entities: {recent}")
    return "\n".join(lines)


def resolve_conversation_continuity(
    session_key: str,
    message: str,
    *,
    language: str = "en",
    image_label: str = "",
    register_entities: bool = True,
) -> ContinuityResolution:
    """
    Resolve what the user is referring to in the current turn.

    Updates short-term session state when ``register_entities`` is True.
  """
    raw = (message or "").strip()
    state = _get_state(session_key)
    state.touch()
    turn_index = state.turn_count + 1
    prior_entities = list(state.entities)

    references = _detect_references(raw)
    has_reference = bool(references)

    if not has_reference and image_label and _IMAGE_REFERENCE_RE.search(raw):
        references = [("image_reference", _IMAGE_REFERENCE_RE, {"categories": ("image",)})]
        has_reference = True

    if not has_reference:
        new_entities = extract_entities(
            raw, turn_index=turn_index, mention_offset=len(state.entities), image_label=image_label
        )
        if register_entities and new_entities:
            _merge_entities(state, new_entities)
        state.turn_count = turn_index
        return ContinuityResolution(
            confidence="none",
            has_reference=False,
            effective_message=raw,
            memory_query=raw,
            active_topic=state.active_topic,
            context_block=_build_context_block(
                confidence="none",
                resolved=None,
                candidates=state.entities,
                active_topic=state.active_topic,
                active_category=state.active_category,
            )
            if state.entities
            else "",
        )

    candidate_pool: list[TrackedEntity] = []
    ref_meta: dict[str, Any] = {}

    for _name, _pattern, meta in references:
        ref_meta.update(meta)
        cats = meta.get("categories")
        pool = _filter_candidates(prior_entities, categories=cats, exclude_user_self=True)
        if meta.get("ordinal") is not None:
            pool_for_ord = _filter_candidates(
                prior_entities,
                categories=("company", "organization", "person", "place", "product", "project"),
                exclude_user_self=True,
            ) or _filter_candidates(prior_entities, exclude_user_self=True)
            picked = _pick_ordinal(pool_for_ord, int(meta["ordinal"]))
            candidate_pool.extend(picked)
        elif pool:
            candidate_pool.append(pool[-1])

    if not candidate_pool and prior_entities:
        candidate_pool = _filter_candidates(prior_entities, exclude_user_self=True)
        if candidate_pool:
            candidate_pool = [candidate_pool[-1]]

    # Deduplicate while preserving order
    dedup_candidates: list[TrackedEntity] = []
    seen: set[str] = set()
    for ent in candidate_pool:
        key = f"{_normalize(ent.text)}::{ent.category}"
        if key not in seen:
            seen.add(key)
            dedup_candidates.append(ent)

    resolved: TrackedEntity | None = None
    confidence: Confidence = "low"
    clarification = ""

    if len(dedup_candidates) == 1:
        resolved = dedup_candidates[0]
        confidence = "high"
        state.active_topic = resolved.text
        state.active_category = resolved.category
    elif len(dedup_candidates) >= 2:
        recent = dedup_candidates[-1]
        resolved = recent
        confidence = "medium"
        state.active_topic = recent.text
        state.active_category = recent.category
        if ref_meta.get("ordinal") is not None and len(dedup_candidates) >= 2:
            # Ordinal with ambiguous pool → clarify
            confidence = "low"
            clarification = _build_clarification(dedup_candidates[-2:], language=language)
            resolved = None
    else:
        confidence = "low"
        if state.entities:
            clarification = _build_clarification(state.entities[-3:], language=language)
        else:
            clarification = (
                "Je ne dispose pas encore d'un sujet actif dans cette conversation. De quoi parlez-vous ?"
                if language == "fr"
                else "I don't have an active topic in this conversation yet. What are you referring to?"
            )

    effective_message = raw
    if resolved and confidence == "high":
        effective_message = f"{raw}\n\n[Continuity: referring to {resolved.label()}]"

    context_block = _build_context_block(
        confidence=confidence,
        resolved=resolved,
        candidates=dedup_candidates or state.entities,
        active_topic=state.active_topic,
        active_category=state.active_category,
    )

    if register_entities:
        state.turn_count = turn_index
        new_entities = extract_entities(
            raw, turn_index=turn_index, mention_offset=len(state.entities), image_label=image_label
        )
        if new_entities:
            _merge_entities(state, new_entities)

    return ContinuityResolution(
        confidence=confidence,
        has_reference=has_reference,
        resolved_entity=resolved,
        candidates=tuple(dedup_candidates),
        clarification=clarification,
        context_block=context_block,
        effective_message=effective_message,
        memory_query=resolved.text if resolved and confidence in ("high", "medium") else raw,
        active_topic=state.active_topic,
    )


def record_turn_entities(session_key: str, message: str, *, image_label: str = "") -> None:
    """Register entities from a message without resolving references (post-turn bookkeeping)."""
    state = _get_state(session_key)
    state.touch()
    turn_index = state.turn_count + 1
    ents = extract_entities(message, turn_index=turn_index, mention_offset=len(state.entities), image_label=image_label)
    if ents:
        _merge_entities(state, ents)
    state.turn_count = turn_index
