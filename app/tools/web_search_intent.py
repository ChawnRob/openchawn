"""Backend web-search intent router (mobile + desktop parity)."""

from __future__ import annotations

import re
import unicodedata

_URL_RE = re.compile(
    r"https?://[^\s<>\"']+|"
    r"www\.[a-z0-9][-a-z0-9.]*\.[a-z]{2,}|"
    r"\b[a-z0-9][-a-z0-9]*\.(?:com|org|net|io|fr|dev|app|co|ai)\b",
    re.IGNORECASE,
)

_GITHUB_REPO_RE = re.compile(
    r"github\.com/[\w.-]+/[\w.-]+|"
    r"\b[\w.-]+/[\w.-]+\b.*\bgithub\b|"
    r"\bgithub\b.*\b[\w.-]+/[\w.-]+\b",
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
    r"\bsync\s+obsidian\b|"
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
    re.compile(r"\bcheck\b", re.IGNORECASE),
    re.compile(r"\bvoir\b.*\bprofil\b", re.IGNORECASE),
)

# P1.1 — strategic / market analyst requests on external entities
_ANALYST_SIGNAL_RE = re.compile(
    r"\b(analys\w*|positionnement|concurrent\w*|marches?\b|business\s*model|"
    r"risques?|opportunite\w*|benchmark\w*|compar\w*)\b",
    re.IGNORECASE,
)

# P1.3 — public discovery: profiles, repos, tech stack, official sites, news
_DISCOVERY_SIGNAL_RE = re.compile(
    r"\b(linkedin|github|git\s*hub|twitter|x\.com|instagram|facebook|"
    r"reseaux\s+sociaux|réseaux\s+sociaux|profil\s+public|profils\s+publics|"
    r"site\s+officiel|official\s+website|fondateur|founder|"
    r"quelle\s+ia\s+utilise|quelles?\s+ia\s+utilis|quels?\s+modeles?\s+ia\s+utilis|"
    r"which\s+ai\s+does|what\s+ai\s+does|tech\s+stack|technolog\w*\s+utilis|"
    r"actualites?|news|repo(?:sitory)?|entreprise\s+actuelle)\b|"
    r"\bet\s+x\b",
    re.IGNORECASE,
)

_TECH_BY_BRAND_RE = re.compile(
    r"\b(ia|ai|intelligence\s+artificielle|modeles?\s+ia|ai\s+models?)\b.*\b(utilise|utilisent|uses|using|adopt)\b|"
    r"\b(utilise|utilisent|uses|using|adopt)\b.*\b(ia|ai|intelligence\s+artificielle|modeles?\s+ia|ai\s+models?)\b",
    re.IGNORECASE,
)

_NEWS_YEAR_RE = re.compile(r"\bactualites?\b.*\b20\d{2}\b|\bnews\b.*\b20\d{2}\b", re.IGNORECASE)

_PROTECTED_PRIVATE_RE = re.compile(
    r"\b(connecte[- ]?toi|log\s*in|login|sign\s*in)\b.*\b(mon|ma|mes|notre)\b|"
    r"\b(mon|ma|mes|notre)\s+(compte\s+)?(linkedin|instagram|facebook|twitter)\b|"
    r"\b(ouvre|open|accede|accède|access)\b.*\b(mon|ma|mes)\s+compte\b|"
    r"\blis\s+(mes|mes)\s+messages\b|"
    r"\b(recupere|récupère|retrieve|fetch|get)\b.*\b(emails?|mails?|messages?)\s+priv|"
    r"\b(emails?|mails?|messages?)\s+priv\w*\b|"
    r"\bprofil\s+prive\b|\bprofil\s+privé\b|\bprivate\s+profile\b|"
    r"\bscrape?\b.*\bprive\b|\bscrape?\b.*\bprivé\b|"
    r"\bderriere\s+connexion\b|\bbehind\s+login\b",
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
        "linkedin", "github", "twitter", "instagram", "facebook", "reseaux", "sociaux",
        "profil", "profils", "public", "publics", "officiel", "actualites", "actualités",
        "aujourd", "hui", "trouve", "recherche", "cherche", "check", "voir",
    }
)

_INTERNAL_BRANDS = frozenset({"coco", "openchawn", "luthor"})
_FRAME_WORDS = frozenset({"mckinsey", "bcg", "bain", "deloitte", "kpmg", "pwc", "ey"})


def _normalize(text: str) -> str:
    t = str(text or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\u2019", "'").replace("'", "'")
    return re.sub(r"\s+", " ", t).strip()


def is_protected_web_request(message: str) -> bool:
    """Private account / authenticated access — never trigger public web search."""
    raw = (message or "").strip()
    if not raw:
        return False
    return bool(_PROTECTED_PRIVATE_RE.search(_normalize(raw)))


def _is_internal_workflow_excluded(normalized: str) -> bool:
    if _AFFINE_OPEN_RE.search(normalized):
        return True
    if _OBSIDIAN_WORKFLOW_RE.search(normalized):
        return True
    if _INTERNAL_SUBJECT_RE.search(normalized):
        return True
    if _INTERNAL_PRODUCT_RE.search(normalized):
        return True
    return False


def _capitalized_entities(raw: str, *, allow_internal_brands: bool = False) -> list[str]:
    found: list[str] = []
    for word in re.findall(r"\b[A-Z][a-zA-Z0-9]{2,}\b", raw):
        low = word.lower()
        if low in _FRAME_WORDS or low in _ANALYSIS_VOCAB:
            continue
        if not allow_internal_brands and low in _INTERNAL_BRANDS:
            continue
        found.append(word)
    return found


def _lowercase_entity_tokens(normalized: str, *, allow_internal_brands: bool = False) -> list[str]:
    tokens = re.findall(r"[a-z0-9][-a-z0-9]*", normalized)
    entities: list[str] = []
    for tok in tokens:
        if len(tok) < 4:
            continue
        if tok in _ANALYSIS_VOCAB or tok in _FRAME_WORDS:
            continue
        if not allow_internal_brands and tok in _INTERNAL_BRANDS:
            continue
        entities.append(tok)
    return entities


def _has_external_entity(raw: str, normalized: str, *, allow_internal_brands: bool = False) -> bool:
    if _URL_RE.search(raw):
        return True
    if _ENTITY_LABEL_RE.search(raw):
        return True
    if _capitalized_entities(raw, allow_internal_brands=allow_internal_brands):
        return True
    if _lowercase_entity_tokens(normalized, allow_internal_brands=allow_internal_brands):
        return True
    return False


def _detect_web_analyst_intent(raw: str, normalized: str) -> bool:
    if not _ANALYST_SIGNAL_RE.search(normalized):
        return False
    return _has_external_entity(raw, normalized)


def _detect_web_discovery_intent(raw: str, normalized: str) -> bool:
    if _GITHUB_REPO_RE.search(raw):
        return True
    if _NEWS_YEAR_RE.search(normalized):
        return True
    if _DISCOVERY_SIGNAL_RE.search(normalized):
        return True
    if _TECH_BY_BRAND_RE.search(normalized) and _has_external_entity(
        raw, normalized, allow_internal_brands=True
    ):
        return True
    if re.search(r"\bqui\s+est\b.*\b(fondateur|founder)\b", normalized):
        return True
    return False


def detect_web_search_intent(message: str) -> bool:
    """True when the user message should trigger the public web search tool."""
    raw = (message or "").strip()
    if not raw:
        return False
    t = _normalize(raw)

    if is_protected_web_request(raw):
        return False
    if _is_internal_workflow_excluded(t):
        return False
    if _URL_RE.search(raw):
        return True
    if any(p.search(t) for p in _WEB_INTENT_PATTERNS):
        return True
    if _detect_web_analyst_intent(raw, t):
        return True
    if _detect_web_discovery_intent(raw, t):
        return True
    return False


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

    gh = _GITHUB_REPO_RE.search(raw)
    if gh:
        return gh.group(0).strip()

    label = _ENTITY_LABEL_RE.search(raw)
    if label:
        entity = label.group(1).strip()
        return f"{entity} company positioning competitors market analysis"

    caps = _capitalized_entities(raw, allow_internal_brands=True)
    if caps and _ANALYST_SIGNAL_RE.search(_normalize(raw)):
        focus = caps[0]
        return f"{focus} product positioning competitors risks opportunities market analysis"

    t = _normalize(raw)
    if "linkedin" in t and caps:
        return f"{caps[0]} LinkedIn public profile"
    if "linkedin" in t:
        return re.sub(r"^(?:recherche|cherche|trouve)\s+", "", raw, flags=re.I).strip() or raw
    if ("github" in t or "git hub" in t) and caps:
        return f"{caps[0]} GitHub repository"
    if "site officiel" in t and caps:
        return f"{caps[0]} official website"
    if _TECH_BY_BRAND_RE.search(t) and caps:
        return f"{caps[0]} AI technology models used today"
    if re.search(r"\bfondateur\b|\bfounder\b", t) and caps:
        return f"{caps[0]} founder"

    q = raw
    for prefix in (
        r"^(?:peux[- ]tu|pourrais[- ]tu|can you|could you|please)\s+",
        r"^(?:recherche|cherche|trouve|search|look up|go to|visit|va sur|visite|voir)\s+",
        r"^(?:les?|des?|du|de la|d['']|the|some)\s+",
    ):
        q = re.sub(prefix, "", q, flags=re.IGNORECASE).strip()

    q = q.rstrip("?.! ")
    return q or raw
