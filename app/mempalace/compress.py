from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from app.mempalace.schema import MemoryEntry
from app.mempalace.store import load_memories, save_memories

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _rank(entry: MemoryEntry) -> float:
    """Entrée 'meilleure' = importance + reuse + confidence."""
    reuse_norm = min(entry.reuse_score / 10.0, 1.0)
    return (
        0.50 * entry.importance_score
        + 0.30 * reuse_norm
        + 0.20 * entry.confidence
    )


@dataclass
class CompressReport:
    total_before: int
    total_after_active: int
    dedup_archived: int
    decay_archived: int
    groups_processed: int


def compress(
    *,
    project: str | None = None,
    dedup_threshold: float = 0.85,
    decay_importance_max: float = 0.3,
    decay_reuse_max: float = 1.0,
    decay_age_days: int = 90,
) -> CompressReport:
    """
    Compresse la mémoire sans appeler de modèle externe.
    - Déduplication Jaccard par (project, type) : garde le meilleur, archive les autres
    - Décroissance : archive les entrées faibles + anciennes
    """
    mems = load_memories()
    total_before = len(mems)
    now = datetime.utcnow()
    dedup_archived = 0
    decay_archived = 0
    groups_processed = 0

    # Ne travaille que sur les entrées actives
    active = [m for m in mems if m.status == "active"]
    if project:
        active = [m for m in active if m.project == project]

    # ─── 1. Déduplication par groupe (project, type) ──────────────────
    buckets: dict[tuple[str, str], list[MemoryEntry]] = {}
    for m in active:
        buckets.setdefault((m.project, m.type), []).append(m)

    for key, bucket in buckets.items():
        if len(bucket) < 2:
            continue
        groups_processed += 1
        bucket.sort(key=_rank, reverse=True)
        kept: list[tuple[MemoryEntry, set[str]]] = []
        for entry in bucket:
            tokens = _tokenize(entry.content) | _tokenize(entry.summary)
            duplicate_of = None
            for ref_entry, ref_tokens in kept:
                if _jaccard(tokens, ref_tokens) >= dedup_threshold:
                    duplicate_of = ref_entry
                    break
            if duplicate_of is None:
                kept.append((entry, tokens))
            else:
                entry.status = "archived"
                entry.summary = (
                    f"[dedup] doublon de {duplicate_of.id[:8]} — {entry.summary}"
                ).strip(" —")
                dedup_archived += 1

    # ─── 2. Décroissance (faible importance + faible réutil + ancien) ──
    age_threshold = now - timedelta(days=decay_age_days)
    for m in active:
        if m.status != "active":
            continue  # déjà archivé en dédup
        if (
            m.importance_score <= decay_importance_max
            and m.reuse_score <= decay_reuse_max
            and datetime.fromisoformat(m.created_at) < age_threshold
        ):
            m.status = "archived"
            m.summary = (m.summary + " [decay]").strip()
            decay_archived += 1

    # Sauvegarde
    save_memories(mems)

    total_after = sum(1 for m in mems if m.status == "active")
    return CompressReport(
        total_before=total_before,
        total_after_active=total_after,
        dedup_archived=dedup_archived,
        decay_archived=decay_archived,
        groups_processed=groups_processed,
    )
