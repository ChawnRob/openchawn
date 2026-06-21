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

# P1.1 — strategic / market analyst requests on external entities
_ANALYST_SIGNAL_RE = re.compile(
    r"\b(analys\w*|positionnement|concurrent\w*|marches?\b|business\s*model|"
    r"risques?|opportunite\w*|benchmark\w*|compar\w*)\b",
    re.IGNORECASE,
)

_INTERNAL_SUBJECT_RE = re.compile(
    r"\b(mon|ma|mes|notre|nos)\s+"
    r"(idee|idée|projet|conversation|image|photo|cours|produit|equipe|équipe|startup|message|texte)\b|"
    r"\b(cette|cet|ce)\s+(image|photo|cours|conversation|fichier|capture|idee|idée)\b",
    re.IGNORECASE,
)

_INTERNAL_PRODUCT_RE = re.compile(
    r"\b(mon|notre|mes|nos)\s+\w*\s*(projet\s+)?(coco|openchawn|luthor)\b|"
    r"\b(analys\w*|compare\w*)\s+(mon|notre|mes|nos)\s+.*\b(coco|openchawn|luthor)\b",
    re.IGNORECASE,
)

_ENTITY_LABEL_RE = re.compile(
    r"(?:entreprise|societe|société|marque|startup|produit)\s*:\s*([A-Za-z0-9][-A-Za-z0-9]*)",
    re.IGNORECASE,
)

# Tokens that signal analysis intent but are not external entity names.
_ANALYSIS_VOCAB = frozenset(
    {
        "analyse", "analyser", "analysez", "analyses", "analyzed", "analyze", "analyzing",
        "positionnement", "concurrent", "concurrents", "concurrente", "marche", "marches",
        "business", "model", "risque", "risques", "opportunite", "opportunites",
        "opportunité", "opportunités", "benchmark", "benchmarks", "compare", "comparer",
        "comparez", "comparaison", "consultant", "consultants", "mckinsey", "mckinsey.",
        "comme", "un", "une", "le", "la", "les", "des", "du", "de", "d", "et", "ou", "pour",
        "avec", "sans", "sur", "dans", "par", "en", "au", "aux", "ce", "cette", "cet", "ces",
        "son", "sa", "ses", "leur", "leurs", "qui", "que", "quoi", "quels", "quel", "quelle",
        "quelles", "sont", "est", "donne", "donnez", "donne-moi", "fais", "fait", "faites",
        "moi", "toi", "lui", "nous", "vous", "ils", "elles", "produit", "produits", "produite",
        "entreprise", "entreprises", "societe", "société", "marche", "marches", "marche.",
        "probables", "probable", "possible", "possibles", "externe", "externes", "strategique",
        "strategiques", "stratégique", "stratégiques", "donnees", "données", "donnee",
        "donnée", "market", "markets", "the", "and", "or", "for", "with", "from", "what",
        "which", "their", "your", "our", "my", "this", "that", "these", "those", "give",
        "please", "could", "would", "should", "about", "into", "versus", "vs",
    }
)

# Internal products — excluded only when clearly user-owned / in-app context.
_INTERNAL_BRANDS = frozenset({"coco", "openchawn", "luthor"})

# Consultant / role words — not treated as external entities.
_FRAME_WORDS = frozenset({"mckinsey", "bcg", "bain", "deloitte", "kpmg", "pwc", "ey"})


def _normalize(text: str) -> str:
    t = str(text or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\u2019", "'").replace("'", "'")
    return re.sub(r"\s+", " ", t).strip()


def _is_internal_analysis_context(normalized: str) -> bool:
    if _INTERNAL_SUBJECT_RE.search(normalized):
        return True
    if _INTERNAL_PRODUCT_RE.search(normalized):
        return True
    return False


def _capitalized_entities(raw: str) -> list[str]:
    found: list[str] = []
    for word in re.findall(r"\b[A-Z][a-zA-Z0-9]{2,}\b", raw):
        low = word.lower()
        if low in _FRAME_WORDS or low in _ANALYSIS_VOCAB:
            continue
        if low in _INTERNAL_BRANDS:
            continue
        found.append(word)
    return found


def _lowercase_entity_tokens(normalized: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][-a-z0-9]*", normalized)
    entities: list[str] = []
    for tok in tokens:
        if len(tok) < 4:
            continue
        if tok in _ANALYSIS_VOCAB or tok in _FRAME_WORDS:
            continue
        if tok in _INTERNAL_BRANDS:
            continue
        entities.append(tok)
    return entities


def _has_external_entity(raw: str, normalized: str) -> bool:
    if _URL_RE.search(raw):
        return True
    if _ENTITY_LABEL_RE.search(raw):
        return True
    if _capitalized_entities(raw):
        return True
    if _lowercase_entity_tokens(normalized):
        return True
    return False


def _detect_web_analyst_intent(raw: str, normalized: str) -> bool:
    """Strategic / competitive analysis on an external company or product."""
    if _is_internal_analysis_context(normalized):
        return False
    if not _ANALYST_SIGNAL_RE.search(normalized):
        return False
    return _has_external_entity(raw, normalized)


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

    if any(p.search(t) for p in _WEB_INTENT_PATTERNS):
        return True

    return _detect_web_analyst_intent(raw, t)


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

    label = _ENTITY_LABEL_RE.search(raw)
    if label:
        entity = label.group(1).strip()
        return f"{entity} company positioning competitors market analysis"

    caps = _capitalized_entities(raw)
    if caps and _ANALYST_SIGNAL_RE.search(_normalize(raw)):
        focus = caps[0]
        return f"{focus} product positioning competitors risks opportunities market analysis"

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
