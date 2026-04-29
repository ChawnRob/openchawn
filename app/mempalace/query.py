from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from app.mempalace.schema import MemoryEntry, MemoryType, MemoryStatus
from app.mempalace.store import load_memories, update_reuse_score

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


@dataclass
class QueryHit:
    entry: MemoryEntry
    score: float
    relevance: float


def _relevance(q_tokens: set[str], e: MemoryEntry) -> float:
    if not q_tokens:
        return 0.0
    e_tokens = _tokenize(e.content) | _tokenize(e.summary)
    if not e_tokens:
        return 0.0
    inter = q_tokens & e_tokens
    union = q_tokens | e_tokens
    return len(inter) / len(union)


def _score(relevance: float, e: MemoryEntry) -> float:
    reuse_norm = min(e.reuse_score / 10.0, 1.0)
    return (
        0.60 * relevance
        + 0.25 * e.importance_score
        + 0.10 * reuse_norm
        + 0.05 * e.confidence
    )


def search_memory(
    query: str,
    *,
    project: Optional[str] = None,
    types: Optional[list[MemoryType]] = None,
    status: MemoryStatus = "active",
    top_k: int = 5,
    min_relevance: float = 0.05,
    touch: bool = True,
) -> list[QueryHit]:
    q_tokens = _tokenize(query)
    hits: list[QueryHit] = []
    for e in load_memories():
        if e.status != status:
            continue
        if project and e.project != project:
            continue
        if types and e.type not in types:
            continue
        rel = _relevance(q_tokens, e)
        if rel < min_relevance:
            continue
        hits.append(QueryHit(entry=e, score=_score(rel, e), relevance=rel))

    hits.sort(key=lambda h: h.score, reverse=True)
    hits = hits[:top_k]

    if touch and hits:
        for h in hits:
            update_reuse_score(h.entry.id, increment=1.0)

    return hits


def has_answer(
    query: str,
    *,
    threshold: float = 0.35,
    project: Optional[str] = None,
    types: Optional[list[MemoryType]] = None,
) -> bool:
    """True => mémoire suffisante, ASI-Evolve n'appelle PAS de modèle."""
    hits = search_memory(
        query, project=project, types=types, top_k=1, touch=False
    )
    return bool(hits) and hits[0].score >= threshold
