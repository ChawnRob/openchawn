"""Backend web-search intent detection (mobile + desktop parity)."""

from __future__ import annotations

import re
import unicodedata

_URL_RE = re.compile(
    r"https?://[^\s<>\"']+|"
    r"www\.[a-z0-9][-a-z0-9.]*\.[a-z]{2,}|"
    r"\b[a-z0-9][-a-z0-9]*\.(?:com|org|net|io|fr|dev|app|co|ai)\b",
    re.IGNORECASE,
)

_AFFINE_OPEN_RE = re.compile(
    r"\b(ouvre|open|lance|launch|demarre|démarre|start)\b.*\b(affine|second\s*brain)\b|"
    r"\b(affine|second\s*brain)\b.*\b(ouvre|open|lance|launch)\b",
    re.IGNORECASE,
)

_OBSIDIAN_WORKFLOW_RE = re.compile(
    r"\b(obsidian)\b.*\b(note|synchron|sync|connect|connec|enregistr|ajoute|range|organis)\w*\b|"
    r"\b(note|synchron|sync|connect|connec|enregistr|ajoute|range|organis)\w*\b.*\b(obsidian)\b|"
    r"\b(range|organis\w*|structure)\w*\s+(ce\s+)?cours\b|"
    r"\bfiche\s+de\s+revis\w+\b|"
    r"\bfais[- ]?moi\s+une\s+fiche\b",
    re.IGNORECASE,
)

_WEB_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brecherche\w*\b", re.IGNORECASE),
    re.compile(r"\bcherche\w*\b", re.IGNORECASE),
    re.compile(r"\btrouve\w*\b", re.IGNORECASE),
    re.compile(r"\bva\s+sur\b", re.IGNORECASE),
    re.compile(r"\bvisite\w*\b", re.IGNORECASE),
    re.compile(r"\bouvre\s+le\s+site\b", re.IGNORECASE),
    re.compile(r"\bderni[eè]res?\s+actualit", re.IGNORECASE),
    re.compile(r"\baujourd['']?hui\b", re.IGNORECASE),
    re.compile(r"\bsite\s+web\b", re.IGNORECASE),
    re.compile(r"\bque\s+fait\b", re.IGNORECASE),
    re.compile(r"\bsearch(?:ing)?\b", re.IGNORECASE),
    re.compile(r"\blook\s+up\b", re.IGNORECASE),
    re.compile(r"\blatest\b", re.IGNORECASE),
    re.compile(r"\bgo\s+to\b", re.IGNORECASE),
    re.compile(r"\bvisit\b", re.IGNORECASE),
    re.compile(r"\bwebsite\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+does\b.*\bdo\b", re.IGNORECASE),
    re.compile(r"\bsummarize\b.*\b(site|page|website)\b", re.IGNORECASE),
    re.compile(r"\br[eé]sume\w*\b.*\b(site|page)\b", re.IGNORECASE),
)


def _normalize(text: str) -> str:
    t = str(text or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\u2019", "'").replace("'", "'")
    return re.sub(r"\s+", " ", t).strip()


def detect_web_search_intent(message: str) -> bool:
    """True when the user message should trigger the web search tool."""
    raw = (message or "").strip()
    if not raw:
        return False
    t = _normalize(raw)

    if _AFFINE_OPEN_RE.search(t):
        return False
    if _OBSIDIAN_WORKFLOW_RE.search(t):
        return False

    if _URL_RE.search(raw):
        return True

    return any(p.search(t) for p in _WEB_INTENT_PATTERNS)


def extract_web_search_query(message: str) -> str:
    """Derive a concise search query from the user message."""
    raw = (message or "").strip()
    if not raw:
        return ""

    url_match = _URL_RE.search(raw)
    if url_match:
        token = url_match.group(0).rstrip(".,;:!?)")
        if re.match(r"^https?://", token, re.IGNORECASE):
            return token
        if token.lower().startswith("www."):
            return "https://" + token
        return f"what is {token} website"

    # Strip common French/EN lead-ins for cleaner provider queries.
    q = raw
    for prefix in (
        r"^(?:peux[- ]tu|pourrais[- ]tu|can you|could you|please)\s+",
        r"^(?:recherche|cherche|trouve|search|look up|go to|visit|va sur|visite)\s+",
        r"^(?:les?|des?|du|de la|d['']|the|some)\s+",
    ):
        q = re.sub(prefix, "", q, flags=re.IGNORECASE).strip()

    q = q.rstrip("?.! ")
    return q or raw
