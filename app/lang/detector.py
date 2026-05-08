import re
import unicodedata

CONFIDENCE_THRESHOLD = 0.50

# ── Marqueurs par langue (sans accents, matchés après normalisation) ────────

_MARKERS: dict[str, list[str]] = {
    "fr": [
        "le", "la", "les", "de", "du", "des", "un", "une", "est", "et",
        "je", "tu", "il", "nous", "vous", "ce", "que", "qui", "dans",
        "pour", "avec", "sur", "pas", "sont", "mon", "ton", "son",
        "mais", "aussi", "cette", "ces", "aux", "ou", "donc", "car",
        "etre", "avoir", "fait", "dire", "comme", "tout", "plus",
        "quel", "quelle", "tres", "bien", "moi", "toi", "elle",
        "pourquoi", "comment", "quand", "bonjour", "salut", "merci",
        "explique",
    ],
    "en": [
        "the", "is", "are", "was", "were", "have", "has", "do", "does",
        "not", "and", "but", "for", "with", "this", "that", "from",
        "they", "you", "we", "can", "will", "would", "should", "could",
        "been", "being", "which", "what", "when", "where", "how", "who",
        "there", "their", "about", "into", "than", "then", "just",
        "it", "my", "your", "our", "an", "hello", "please", "think",
        "know", "want", "need", "help", "explain", "tell", "why",
        "hi", "hey", "name", "thanks", "thank", "yes", "how", "are",
    ],
    "es": [
        "el", "los", "las", "del", "una", "es", "y", "en", "que", "por",
        "con", "para", "como", "mas", "pero", "su", "al", "lo", "se",
        "no", "son", "esta", "este", "todo", "tiene", "hay", "fue",
        "ser", "hacer", "puede", "desde", "muy", "hola", "hoy",
        "quiero", "sobre", "tambien", "cuando", "donde", "estoy",
        "porque", "tengo", "mi", "tu", "nos", "ellos", "llama",
        "bien", "gracias", "bueno", "buena", "siempre", "nunca",
        "te", "me", "le", "yo", "ella", "usted", "somos",
    ],
    "de": [
        "der", "die", "das", "ein", "eine", "ist", "und", "nicht",
        "von", "mit", "auf", "fur", "den", "dem", "des", "sich",
        "ich", "sie", "wir", "auch", "nach", "wird", "bei", "noch",
        "aber", "wie", "wenn", "oder", "dass", "diese", "kann", "sein",
        "heute", "sehr", "bin", "hat", "haben", "mein", "dein",
        "funktioniert", "warum", "bitte", "danke", "gut", "ja", "nein",
    ],
    "pt": [
        "do", "da", "dos", "das", "um", "uma", "os", "as", "no",
        "na", "em", "que", "por", "com", "para", "como", "mais", "mas",
        "seu", "sua", "ele", "ela", "sao", "esta", "tem", "ser", "ter",
        "voce", "hoje", "ola", "muito", "bem", "nao", "isso",
        "obrigado", "obrigada", "bom", "boa", "sempre", "nunca",
        "eu", "nos", "eles", "onde", "quando", "porque", "tudo",
    ],
    "it": [
        "il", "lo", "le", "di", "del", "della", "un", "una",
        "che", "non", "con", "per", "sono", "come", "anche", "piu",
        "questo", "questa", "suo", "sua", "essere", "fare", "molto",
        "ciao", "oggi", "bene", "tutto", "sempre", "dove", "quando",
        "grazie", "buono", "buona", "stai", "sto", "sei", "siamo",
        "perche", "cosa", "chi", "mi", "ti", "ci", "si",
    ],
}

# Texte court typiquement anglais (hello, how are you, …)
_EN_HIGH_SIGNAL: frozenset[str] = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "how",
        "are",
        "you",
        "what",
        "name",
        "thanks",
        "please",
        "yes",
        "no",
        "ok",
        "sure",
    }
)

# ── Caractères discriminants (EXCLUSIFS à chaque langue autant que possible) ──

_CHAR_HINTS: dict[str, list[str]] = {
    "fr": ["œ", "û", "ê", "î", "ô", "â", "ë", "ï"],
    "es": ["ñ", "¿", "¡"],
    "de": ["ß", "ä", "ö", "ü"],
    "pt": ["ã", "õ"],
    "it": ["ù", "ò"],
}

_LANG_NAMES = {
    "fr": "français",
    "en": "anglais",
    "es": "espagnol",
    "de": "allemand",
    "pt": "portugais",
    "it": "italien",
    "und": "unknown",
}


# ── Normalisation et tokenisation ──────────────────────────────────────────

def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _tokenize(text: str) -> set[str]:
    cleaned = _strip_accents(text.lower())
    cleaned = cleaned.replace("'", " ").replace("`", " ")
    return set(re.findall(r"[a-z]+", cleaned))


def _english_short_phrase_confidence(word_set: set[str], raw: str) -> float | None:
    """Boost anglais pour messages très courts (1–2 tokens) sans signal FR."""
    if len(word_set) > 3:
        return None
    if re.search(r"[àâäéèêëïîôùûçœ]", raw.lower()):
        return None
    intersection = word_set & _EN_HIGH_SIGNAL
    if not intersection:
        return None
    if len(word_set) <= 1 and list(word_set)[0] in _EN_HIGH_SIGNAL:
        return 0.82
    if len(intersection) >= 2 or (len(word_set) <= 3 and intersection):
        return 0.75
    return None


# ── Scoring ────────────────────────────────────────────────────────────────

def _word_exclusivity(word: str) -> float:
    """Poids d'un mot : 1.0 si exclusif à une langue, réduit si partagé."""
    count = sum(1 for markers in _MARKERS.values() if word in set(markers))
    if count <= 1:
        return 1.0
    return 1.0 / count  # partagé entre 2 langues → 0.5, 3 → 0.33, etc.


def _score_markers(word_set: set[str]) -> dict[str, float]:
    """Score pondéré : mots exclusifs comptent plus que mots partagés."""
    n_words = len(word_set)
    if n_words == 0:
        return {lang: 0.0 for lang in _MARKERS}

    scores: dict[str, float] = {}
    for lang, markers in _MARKERS.items():
        marker_set = set(markers)
        matched = word_set & marker_set
        weighted = sum(_word_exclusivity(w) for w in matched)
        scores[lang] = weighted / n_words
    return scores


def _score_chars(original_text: str) -> dict[str, float]:
    """Bonus par caractères discriminants dans le texte original."""
    text_lower = original_text.lower()
    bonuses: dict[str, float] = {}
    for lang, chars in _CHAR_HINTS.items():
        hits = sum(1 for c in chars if c in text_lower)
        if hits > 0:
            bonuses[lang] = 0.15 * min(hits, 3)
    return bonuses


def _fr_vs_en_preference(word_set: set[str], raw: str) -> str | None:
    """Si anglais et français sont proches, ne pas imposer ``fr`` si l'anglais est plausible."""
    if not word_set:
        return None
    en_m = word_set & set(_MARKERS["en"])
    fr_m = word_set & set(_MARKERS["fr"])
    if not en_m:
        return None
    fr_bonus = len(re.findall(r"[àâäéèêëïîôùûçœ]", raw)) * 2
    adj_en = len(en_m)
    adj_fr = len(fr_m) + fr_bonus / max(len(word_set), 1)
    if adj_en >= adj_fr and adj_en >= 1:
        return "en"
    if adj_fr > adj_en:
        return "fr"
    return "en"


def _compute_confidence(scores: dict[str, float]) -> tuple[str, float]:
    """Confiance basée sur le score absolu ET l'écart avec le 2ème."""
    sorted_langs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_lang, best_score = sorted_langs[0]

    if best_score == 0:
        return "und", 0.0

    if len(sorted_langs) < 2 or sorted_langs[1][1] == 0:
        return best_lang, 1.0

    second_score = sorted_langs[1][1]
    gap_ratio = (best_score - second_score) / best_score  # 0..1

    confidence = (best_score * 0.6) + (gap_ratio * 0.4)
    return best_lang, round(min(confidence, 1.0), 2)


# ── API publique ───────────────────────────────────────────────────────────

class LangResult:
    __slots__ = ("lang", "confidence", "source")

    def __init__(self, lang: str, confidence: float, source: str):
        self.lang = lang
        self.confidence = confidence
        self.source = source

    def to_dict(self) -> dict:
        return {
            "lang": self.lang,
            "lang_confidence": self.confidence,
            "lang_source": self.source,
        }


def detect_language(
    text: str,
    user_cache: dict[str, str] | None = None,
    user_id: str = "",
) -> LangResult:
    """
    Détection de langue — fallback **jamais** ``fr`` par défaut sur signal vide ou ambigu
    quand des marqueurs anglais clairs sont présents.
    """
    raw = (text or "").strip()
    word_set = _tokenize(raw)

    if len(word_set) < 2:
        short_conf = _english_short_phrase_confidence(word_set, raw)
        if short_conf is not None:
            return LangResult("en", short_conf, "short_english_phrase")
        if user_cache and user_id and user_id in user_cache:
            return LangResult(user_cache[user_id], 0.0, "cached")
        if len(word_set) == 1:
            w = next(iter(word_set))
            if w in _MARKERS["en"] and w not in _MARKERS["fr"]:
                return LangResult("en", 0.72, "single_en_marker")
        return LangResult("und", 0.0, "fallback_unknown")

    marker_scores = _score_markers(word_set)
    char_bonuses = _score_chars(raw)

    combined: dict[str, float] = {}
    for lang in marker_scores:
        combined[lang] = marker_scores[lang] + char_bonuses.get(lang, 0.0)

    pref = _fr_vs_en_preference(word_set, raw)
    if pref == "en":
        combined["en"] = combined.get("en", 0.0) + 0.12
    elif pref == "fr":
        combined["fr"] = combined.get("fr", 0.0) + 0.12

    best_lang, confidence = _compute_confidence(combined)
    if best_lang == "und" and confidence == 0.0:
        return LangResult("und", 0.0, "fallback_unknown")

    if confidence >= CONFIDENCE_THRESHOLD:
        return LangResult(best_lang, confidence, "detected")

    if user_cache and user_id and user_id in user_cache:
        return LangResult(user_cache[user_id], confidence, "cached")

    return LangResult("und", confidence, "fallback_unknown")


def get_language_name(code: str) -> str:
    if not str(code or "").strip():
        return "unknown"
    c = str(code).strip().lower()
    return _LANG_NAMES.get(c, str(code))
