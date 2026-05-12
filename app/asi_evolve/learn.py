from __future__ import annotations
import re
from typing import Optional
from app.mempalace import add_memory, search_memory, MemoryEntry
from app.mempalace.store import load_memories

# ─── Seuils ──────────────────────────────────────────────────────────────
_MIN_RESPONSE_LEN = 30        # réponses trop courtes = aucun signal
_MAX_CONTENT_LEN = 2000       # tronque les gros blocs
_DUPLICATE_THRESHOLD = 0.60   # si une mémoire proche existe déjà → skip

# ─── Patterns rédaction (secrets) ────────────────────────────────────────
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|Bearer\s+[A-Za-z0-9._\-]{20,}|"
    r"api[_-]?key\s*[:=]\s*\S+|token\s*[:=]\s*\S+|"
    r"password\s*[:=]\s*\S+|secret\s*[:=]\s*\S+)",
    re.IGNORECASE,
)

_TIER_IMPORTANCE = {
    "premium":  0.70,
    "economic": 0.55,
    "local":    0.45,
}


def _redact(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text or "")


def _summarize(prompt: str, response: str, max_len: int = _MAX_CONTENT_LEN) -> str:
    q = prompt.strip().replace("\n", " ")
    a = response.strip()
    blob = f"Q: {q}\nR: {a}"
    if len(blob) > max_len:
        blob = blob[:max_len].rstrip() + " …"
    return _redact(blob)


def learn_from_exchange(
    prompt: str,
    response: str,
    *,
    provider: str,
    tier: str = "economic",
    project: str = "openchawn",
    user_id: str = "robert",
) -> Optional[MemoryEntry]:
    """
    Consolide un échange Q/R réussi en une entrée MemPalace 'fact'.
    Retourne None si l'entrée n'apporte pas de valeur (erreur, trop court, doublon).
    """
    if not response or response.startswith("[ERREUR]"):
        return None
    clean = response.strip()
    if len(clean) < _MIN_RESPONSE_LEN:
        return None

    # Dédup stricte d'abord sur le prompt déjà mémorisé pour éviter une seconde
    # écriture identique lorsque la recherche heuristique ne score pas assez haut.
    norm_summary = _redact(prompt.strip().replace("\n", " "))[:200]
    for row in load_memories():
        if row.project != project:
            continue
        if (row.summary or "") == norm_summary:
            return None

    # Dédup heuristique : ne pas réécrire une entrée quasi-identique
    existing = search_memory(prompt, project=project, top_k=1, touch=False)
    if existing and existing[0].score >= _DUPLICATE_THRESHOLD:
        return None

    importance = _TIER_IMPORTANCE.get(tier, 0.5)
    content = _summarize(prompt, clean)
    summary = norm_summary

    return add_memory(
        content=content,
        type="fact",
        project=project,
        summary=summary,
        importance_score=importance,
        confidence=0.75,
        source=f"auto_learn:{provider}",
    )
