"""
Embedding cache local V11.6.

- Cache persistant basé sur hash du texte normalisé.
- N'enregistre jamais de texte brut.
- Bloque la mise en cache pour contenu sensible (secret/token/api key).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from threading import Lock
from typing import Any

from app.memory import fractal_memory as fm

_CACHE_PATH = Path("data/memory/semantic/embedding_cache.json")
_LOCK = Lock()
_MAX_ITEMS = 30000
_CACHE_STATS = {"hits": 0, "misses": 0, "sets": 0, "blocked_sensitive": 0}


def _ensure_dir() -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_cache() -> dict[str, Any]:
    if not _CACHE_PATH.exists():
        return {"status": "ok", "items": {}}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "error", "items": {}}


def _save_cache(data: dict[str, Any]) -> None:
    _ensure_dir()
    _CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_text(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s[:5000]


def compute_text_hash(text: str) -> str:
    norm = _normalize_text(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def get_cached_embedding(text_hash: str) -> dict[str, Any] | None:
    h = str(text_hash or "").strip()
    if not h:
        return None
    with _LOCK:
        data = _load_cache()
        items = data.get("items") if isinstance(data.get("items"), dict) else {}
        row = items.get(h)
        if isinstance(row, dict) and isinstance(row.get("vector"), list):
            _CACHE_STATS["hits"] += 1
            return {"vector": row.get("vector"), "metadata": row.get("metadata") or {}, "cached_at": row.get("cached_at")}
        _CACHE_STATS["misses"] += 1
        return None


def set_cached_embedding(text_hash: str, vector: list[float], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    h = str(text_hash or "").strip()
    vec = [float(x) for x in (vector or [])]
    md = dict(metadata or {})
    if not h or not vec:
        return {"status": "error", "detail": "invalid_payload"}

    # Safety: never cache if caller flags content as sensitive.
    txt_hint = str(md.get("text_preview") or "")
    if txt_hint and fm._contains_sensitive_text(txt_hint):  # noqa: SLF001
        with _LOCK:
            _CACHE_STATS["blocked_sensitive"] += 1
        return {"status": "skipped", "reason": "sensitive_content"}
    md.pop("text_preview", None)

    with _LOCK:
        data = _load_cache()
        items = data.get("items") if isinstance(data.get("items"), dict) else {}
        items[h] = {
            "vector": vec,
            "metadata": md,
            "cached_at": time.time(),
        }
        if len(items) > _MAX_ITEMS:
            ordered = sorted(items.items(), key=lambda kv: float((kv[1] or {}).get("cached_at") or 0.0), reverse=True)
            items = dict(ordered[:_MAX_ITEMS])
        data["status"] = "ok"
        data["items"] = items
        data["updated_at"] = time.time()
        _save_cache(data)
        _CACHE_STATS["sets"] += 1
    return {"status": "ok"}


def embedding_cache_stats() -> dict[str, Any]:
    with _LOCK:
        data = _load_cache()
        items = data.get("items") if isinstance(data.get("items"), dict) else {}
        return {
            "status": "ok",
            "items_count": len(items),
            "path": str(_CACHE_PATH),
            "hits": int(_CACHE_STATS["hits"]),
            "misses": int(_CACHE_STATS["misses"]),
            "sets": int(_CACHE_STATS["sets"]),
            "blocked_sensitive": int(_CACHE_STATS["blocked_sensitive"]),
            "updated_at": float(data.get("updated_at") or 0.0),
            "max_items": _MAX_ITEMS,
        }

