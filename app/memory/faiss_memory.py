"""
FAISS Semantic Retrieval Layer V11.6 (hybrid, complémentaire).

- N'écrase jamais le retrieval fractal/timeline.
- Embeddings locaux uniquement (via embedding_provider).
- Support fallback sans FAISS pour tests locaux.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.language_policy import detect_user_language
from app.memory import embedding_cache as ec
from app.memory import embedding_provider as ep
from app.memory import fractal_memory as fm

_SEM_DIR = Path("data/memory/semantic")
_FAISS_INDEX_PATH = _SEM_DIR / "faiss.index"
_META_PATH = _SEM_DIR / "faiss_meta.json"
_LOCK = Lock()
_MAX_SEARCH_K = 128
_MAX_INDEX_ITEMS = 25000


def _ensure_dir() -> None:
    _SEM_DIR.mkdir(parents=True, exist_ok=True)


def _entry_text(e: dict) -> str:
    return " ".join(
        [
            str(e.get("summary") or ""),
            str(e.get("user_message") or ""),
            str(e.get("assistant_response") or ""),
            " ".join([str(t) for t in (e.get("tags") or []) if str(t).strip()]),
            str(e.get("project_name") or e.get("project") or ""),
        ]
    ).strip()


def _entry_metadata(e: dict) -> dict[str, Any]:
    txt = _entry_text(e)
    return {
        "project_name": str(e.get("project_name") or e.get("project") or ""),
        "memory_type": str(e.get("memory_type") or ""),
        "language": detect_user_language(txt),
        "archived": str(e.get("lifecycle_status") or "") == fm.MEMORY_LIFECYCLE_ARCHIVED,
        "contradicted": bool(e.get("contradiction_detected")),
        "summary": str(e.get("summary") or "")[:620],
        "importance_score": float(e.get("importance_score") or 0.0),
        "timestamp": str(e.get("timestamp") or ""),
    }


def _load_meta() -> dict[str, Any]:
    if not _META_PATH.exists():
        return {
            "status": "empty",
            "dimension": 0,
            "provider": "none",
            "vectors_count": 0,
            "items": [],
            "updated_at": 0.0,
        }
    try:
        return json.loads(_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status": "error",
            "dimension": 0,
            "provider": "none",
            "vectors_count": 0,
            "items": [],
            "updated_at": 0.0,
        }


def _save_meta(meta: dict[str, Any]) -> None:
    _ensure_dir()
    _META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _cos(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 or nb <= 1e-12:
        return -1.0
    return dot / (na * nb)


def _faiss_available():
    try:
        import faiss  # type: ignore

        return faiss
    except Exception:
        return None


def _write_faiss_index(vectors: list[list[float]]) -> dict[str, Any]:
    faiss = _faiss_available()
    if not faiss or not vectors:
        return {"stored_with": "meta_only"}
    try:
        import numpy as np  # type: ignore

        mat = np.array(vectors, dtype="float32")
        dim = mat.shape[1]
        idx = faiss.IndexFlatIP(dim)
        idx.add(mat)
        _ensure_dir()
        faiss.write_index(idx, str(_FAISS_INDEX_PATH))
        return {"stored_with": "faiss_index"}
    except Exception:
        return {"stored_with": "meta_only"}


def _search_with_faiss(query_vec: list[float], top_k: int, vectors_count: int) -> list[tuple[int, float]]:
    faiss = _faiss_available()
    if not faiss or not _FAISS_INDEX_PATH.exists() or not query_vec:
        return []
    try:
        import numpy as np  # type: ignore

        q = np.array([query_vec], dtype="float32")
        idx = faiss.read_index(str(_FAISS_INDEX_PATH))
        k = max(1, min(int(top_k), max(1, vectors_count)))
        d, i = idx.search(q, k)
        out: list[tuple[int, float]] = []
        for pos, score in zip(i[0].tolist(), d[0].tolist()):
            if int(pos) < 0:
                continue
            out.append((int(pos), float(score)))
        return out
    except Exception:
        return []


def _match_filters(md: dict[str, Any], filters: dict[str, Any]) -> bool:
    for k in ("project_name", "memory_type", "language"):
        v = filters.get(k)
        if v is None or v == "":
            continue
        if str(md.get(k) or "") != str(v):
            return False
    for k in ("archived", "contradicted"):
        if k not in filters or filters.get(k) is None:
            continue
        if bool(md.get(k)) != bool(filters.get(k)):
            return False
    return True


def _sanitize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    f = dict(filters or {})
    out: dict[str, Any] = {}
    for k in ("project_name", "memory_type", "language"):
        v = str(f.get(k) or "").strip()
        if v:
            out[k] = v
    for k in ("archived", "contradicted"):
        if k in f and f.get(k) is not None:
            out[k] = bool(f.get(k))
    return out


def build_faiss_index(entries: list[dict] | None = None) -> dict[str, Any]:
    with _LOCK:
        t0 = time.perf_counter()
        if entries is None:
            entries = fm.entries_snapshot_for_tests()
        pool = [fm._ensure_entry_defaults(dict(e)) for e in (entries or [])]  # noqa: SLF001
        pool.sort(
            key=lambda e: (
                1.0 if str(e.get("temporal_status") or "") in ("rising", "stable") else 0.0,
                float(e.get("long_term_value") or 0.0),
                float(e.get("importance_score") or 0.0),
                str(e.get("timestamp") or ""),
            ),
            reverse=True,
        )
        items: list[dict[str, Any]] = []
        texts: list[str] = []
        for e in pool[:_MAX_INDEX_ITEMS]:
            if not e.get("id"):
                continue
            if e.get("indexable") is False:
                continue
            if str(e.get("contradiction_resolution_status") or "") == "deprecated":
                continue
            txt = _entry_text(e)
            if not txt:
                continue
            if fm._contains_sensitive_text(txt):  # noqa: SLF001
                continue
            items.append(
                {
                    "vector_id": len(items),
                    "memory_id": str(e.get("id")),
                    "metadata": _entry_metadata(e),
                }
            )
            texts.append(txt[:2400])

        emb = ep.embed_batch(texts)
        vectors = emb.get("vectors") or []
        dim = int(emb.get("dimension") or 0)

        if len(vectors) != len(items):
            n = min(len(vectors), len(items))
            vectors = vectors[:n]
            items = items[:n]

        idx_rep = _write_faiss_index(vectors)
        meta = {
            "status": "ok",
            "dimension": dim,
            "provider": str(emb.get("provider") or "unknown"),
            "vectors_count": len(items),
            "items": items,
            "vectors_fallback": vectors,
            "index_storage": idx_rep.get("stored_with"),
            "updated_at": time.time(),
            "build_elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "index_limit": _MAX_INDEX_ITEMS,
        }
        _save_meta(meta)
        return {
            "status": "ok",
            "vectors_count": len(items),
            "dimension": dim,
            "provider": meta["provider"],
            "index_storage": meta["index_storage"],
            "elapsed_ms": meta["build_elapsed_ms"],
        }


def rebuild_semantic_index(*, incremental: bool = False) -> dict[str, Any]:
    if not incremental:
        return build_faiss_index()
    entries = fm.entries_snapshot_for_tests()
    with _LOCK:
        meta = _load_meta()
        existing = {str(x.get("memory_id") or "") for x in (meta.get("items") or []) if x.get("memory_id")}
    added = 0
    for e in entries:
        mid = str(e.get("id") or "")
        if not mid or mid in existing:
            continue
        rep = add_memory_embedding(e)
        if rep.get("status") == "ok" and rep.get("added") is True:
            added += 1
    return {"status": "ok", "mode": "incremental", "added": added, "vectors_count": get_semantic_index_stats().get("vectors_count")}


def add_memory_embedding(memory_entry: dict) -> dict[str, Any]:
    mid = str((memory_entry or {}).get("id") or "").strip()
    if not mid:
        return {"status": "error", "detail": "missing_memory_id"}
    with _LOCK:
        meta = _load_meta()
        items = list(meta.get("items") or [])
        vectors = list(meta.get("vectors_fallback") or [])
        items = [x for x in items if str(x.get("memory_id") or "") != mid]
        if vectors and len(vectors) >= len(items):
            vectors = [v for i, v in enumerate(vectors) if i < len(items)]

        txt = _entry_text(memory_entry)
        if memory_entry.get("indexable") is False:
            return {"status": "ok", "added": False, "reason": "non_indexable"}
        if str(memory_entry.get("contradiction_resolution_status") or "") == "deprecated":
            return {"status": "ok", "added": False, "reason": "deprecated"}
        if not txt or fm._contains_sensitive_text(txt):  # noqa: SLF001
            meta["items"] = items
            meta["vectors_fallback"] = vectors
            meta["vectors_count"] = len(items)
            _save_meta(meta)
            return {"status": "ok", "added": False, "reason": "empty_or_sensitive"}

        txt_short = txt[:2400]
        text_hash = ec.compute_text_hash(txt_short)
        hit = ec.get_cached_embedding(text_hash)
        cache_hit = bool(hit and isinstance(hit.get("vector"), list))
        if cache_hit:
            vec = [float(x) for x in (hit.get("vector") or [])]
            provider_name = str((hit.get("metadata") or {}).get("provider") or "embedding_cache")
        else:
            emb = ep.embed_text(txt_short)
            vec = emb.get("vector") or []
            provider_name = str(emb.get("provider") or "unknown")
            if vec:
                ec.set_cached_embedding(
                    text_hash,
                    vec,
                    metadata={
                        "provider": provider_name,
                        "dimension": len(vec),
                        # Preview only for sensitive screening, never persisted in cache.
                        "text_preview": txt_short[:180],
                    },
                )
        if not vec:
            return {"status": "error", "detail": "embedding_failed"}

        item = {
            "vector_id": len(items),
            "memory_id": mid,
            "metadata": _entry_metadata(memory_entry),
        }
        items.append(item)
        vectors.append(vec)
        for i, it in enumerate(items):
            it["vector_id"] = i

        idx_rep = _write_faiss_index(vectors)
        meta.update(
            {
                "status": "ok",
                "dimension": len(vec),
                "provider": provider_name,
                "vectors_count": len(items),
                "items": items,
                "vectors_fallback": vectors,
                "index_storage": idx_rep.get("stored_with"),
                "updated_at": time.time(),
            }
        )
        _save_meta(meta)
        return {"status": "ok", "added": True, "memory_id": mid, "cache_hit": cache_hit}


def remove_memory_embedding(memory_id: str) -> dict[str, Any]:
    mid = str(memory_id or "").strip()
    if not mid:
        return {"status": "error", "detail": "missing_memory_id"}
    with _LOCK:
        meta = _load_meta()
        items = list(meta.get("items") or [])
        vectors = list(meta.get("vectors_fallback") or [])

        kept_items: list[dict[str, Any]] = []
        kept_vectors: list[list[float]] = []
        removed = 0
        for i, it in enumerate(items):
            if str(it.get("memory_id") or "") == mid:
                removed += 1
                continue
            kept_items.append(it)
            if i < len(vectors):
                kept_vectors.append(vectors[i])
        for i, it in enumerate(kept_items):
            it["vector_id"] = i

        idx_rep = _write_faiss_index(kept_vectors)
        meta["items"] = kept_items
        meta["vectors_fallback"] = kept_vectors
        meta["vectors_count"] = len(kept_items)
        meta["index_storage"] = idx_rep.get("stored_with")
        meta["updated_at"] = time.time()
        _save_meta(meta)
        return {"status": "ok", "removed": removed}


def search_semantic_memory(
    query: str,
    *,
    top_k: int = 8,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    q = (query or "").strip()
    if not q:
        return {"status": "ok", "results": [], "query": "", "elapsed_ms": 0.0}
    with _LOCK:
        meta = _load_meta()
        items = list(meta.get("items") or [])
        vectors = list(meta.get("vectors_fallback") or [])
        if not items:
            return {"status": "ok", "results": [], "query": q, "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2)}
        emb = ep.embed_text(q)
        qv = emb.get("vector") or []
        if not qv:
            return {"status": "ok", "results": [], "query": q, "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2)}

        k_eff = max(1, min(int(top_k), _MAX_SEARCH_K))
        raw = _search_with_faiss(qv, top_k=k_eff * 3, vectors_count=len(items))
        used_backend = "faiss"
        if not raw:
            used_backend = "bruteforce_fallback"
            brute: list[tuple[int, float]] = []
            for i, v in enumerate(vectors):
                brute.append((i, _cos(qv, v)))
            brute.sort(key=lambda x: x[1], reverse=True)
            raw = brute[: max(1, min(k_eff * 3, len(brute)))]

        f = _sanitize_filters(filters)
        out: list[dict[str, Any]] = []
        for pos, score in raw:
            if pos < 0 or pos >= len(items):
                continue
            it = items[pos]
            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            if not _match_filters(md, f):
                continue
            out.append(
                {
                    "vector_id": int(it.get("vector_id") or pos),
                    "memory_id": str(it.get("memory_id") or ""),
                    "score": float(score),
                    "metadata": md,
                }
            )
            if len(out) >= k_eff:
                break
        return {
            "status": "ok",
            "query": q,
            "results": out,
            "provider": emb.get("provider"),
            "backend": used_backend,
            "effective_top_k": k_eff,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }


def semantic_candidates_for_query(
    entries: list[dict],
    query: str,
    *,
    limit: int = 4,
    filters: dict[str, Any] | None = None,
    semantic_boost: float = 0.2,
    contradiction_mode: str = "off",
    policy_bundle: dict[str, Any] | None = None,
    cognitive_state: str = "stable",
) -> list[dict]:
    res = search_semantic_memory(query, top_k=max(1, limit * 3), filters=filters)
    by_id = {str(e.get("id") or ""): e for e in entries if e.get("id")}
    out: list[dict] = []
    seen: set[str] = set()
    st = str(cognitive_state or "stable").lower()
    policy_hint = str((policy_bundle or {}).get("compression_level") or "none")
    for i, row in enumerate(res.get("results") or []):
        mid = str(row.get("memory_id") or "")
        if not mid or mid in seen:
            continue
        e = by_id.get(mid)
        if not e:
            continue
        if contradiction_mode == "off" and bool(e.get("contradiction_detected")):
            continue
        if not fm.is_active_memory(e) and not bool((filters or {}).get("archived")):
            continue
        c = dict(e)
        score = float(row.get("score") or 0.0)
        eff_boost = float(semantic_boost)
        if st == "overloaded":
            eff_boost *= 0.75
        elif st in ("exploring", "focused"):
            eff_boost *= 1.08
        dbg = {
            "why_selected": (
                "layer:semantic;semantic_similarity;hybrid_additive;"
                f"semantic_boost={round(eff_boost,3)};cognitive_state={st};policy={policy_hint}"
            ),
            "semantic_score": round(score, 4),
            "semantic_boost": round(eff_boost, 3),
            "relevance_score": 0,
            "importance_score": float(e.get("importance_score") or 0.0),
            "decay_score": float(e.get("decay_score") or 0.0),
            "memory_type": str(e.get("memory_type") or ""),
            "retrieval_rank": 0,
            "composite_score": round((score * 100.0) + eff_boost * 10.0, 2),
        }
        c["_retrieval_debug"] = dbg
        out.append(c)
        seen.add(mid)
        if len(out) >= max(1, limit):
            break
    return out


def get_semantic_index_stats() -> dict[str, Any]:
    with _LOCK:
        meta = _load_meta()
        items = list(meta.get("items") or [])
        by_project: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_lang: dict[str, int] = {}
        for it in items:
            md = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            p = str(md.get("project_name") or "")
            t = str(md.get("memory_type") or "")
            l = str(md.get("language") or "")
            by_project[p] = by_project.get(p, 0) + 1
            by_type[t] = by_type.get(t, 0) + 1
            by_lang[l] = by_lang.get(l, 0) + 1
        return {
            "status": "ok",
            "vectors_count": int(meta.get("vectors_count") or len(items)),
            "dimension": int(meta.get("dimension") or 0),
            "provider": str(meta.get("provider") or "unknown"),
            "index_storage": str(meta.get("index_storage") or "meta_only"),
            "updated_at": float(meta.get("updated_at") or 0.0),
            "index_file_exists": _FAISS_INDEX_PATH.exists(),
            "meta_file_exists": _META_PATH.exists(),
            "max_search_k": _MAX_SEARCH_K,
            "max_index_items": _MAX_INDEX_ITEMS,
            "projects": by_project,
            "memory_types": by_type,
            "languages": by_lang,
        }

