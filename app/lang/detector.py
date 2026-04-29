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
}


# ── Normalisation et tokenisation ──────────────────────────────────────────

def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _tokenize(text: str) -> set[str]:
    cleaned = _strip_accents(text.lower())
    return set(re.findall(r"[a-z]+", cleaned))


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


def _compute_confidence(scores: dict[str, float]) -> tuple[str, float]:
    """Confiance basée sur le score absolu ET l'écart avec le 2ème."""
    sorted_langs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_lang, best_score = sorted_langs[0]

    if best_score == 0:
        return "fr", 0.0

    if len(sorted_langs) < 2 or sorted_langs[1][1] == 0:
        return best_lang, 1.0

    second_score = sorted_langs[1][1]
    gap_ratio = (best_score - second_score) / best_score  # 0..1

    # Confiance = combinaison score absolu (poids fort) + écart relatif
    # Score absolu dominant : si le modèle reconnaît beaucoup de mots → confiant
    # Gap relatif : si le 2ème est loin → encore plus confiant
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


def detect_language(text: str, user_cache: dict[str, str] | None = None,
                    user_id: str = "") -> LangResult:
    """
    Détection de langue production-ready.

    Pipeline :
      1. Tokenisation + normalisation unicode
      2. Scoring marqueurs (proportion de mots reconnus) + caractères discriminants
      3. Calcul confiance (écart relatif entre top 2)
      4. Si confiance >= 0.65 → langue détectée
      5. Si confiance < 0.65 → cache user ou fallback fr
    """
    word_set = _tokenize(text)

    if len(word_set) < 2:
        if user_cache and user_id and user_id in user_cache:
            return LangResult(user_cache[user_id], 0.0, "cached")
        return LangResult("fr", 0.0, "fallback_default")

    # Scoring
    marker_scores = _score_markers(word_set)
    char_bonuses = _score_chars(text)

    combined: dict[str, float] = {}
    for lang in marker_scores:
        combined[lang] = marker_scores[lang] + char_bonuses.get(lang, 0.0)

    best_lang, confidence = _compute_confidence(combined)

    if confidence >= CONFIDENCE_THRESHOLD:
        return LangResult(best_lang, confidence, "detected")

    # Confiance trop faible → cache user si dispo
    if user_cache and user_id and user_id in user_cache:
        return LangResult(user_cache[user_id], confidence, "cached")

    return LangResult("fr", confidence, "fallback_default")


def get_language_name(code: str) -> str:
    return _LANG_NAMES.get(code, "français")
