"""
Semantic indexing worker V11.6 (in-process, best-effort).

- Ne bloque jamais /chat.
- Queue locale thread-safe.
- Compatible futur scheduler externe (Railway/Redis worker) sans changement API.
"""

from __future__ import annotations

import copy
import time
from collections import deque
from threading import Lock
from typing import Any

from app.memory import faiss_memory as fsm
from app.memory import fractal_memory as fm

_LOCK = Lock()
_QUEUE: deque[str] = deque()
_IN_QUEUE: set[str] = set()
_STATUS: dict[str, Any] = {
    "pending": 0,
    "indexed": 0,
    "skipped": 0,
    "errors": 0,
    "last_run_at": None,
    "last_error": "",
    "last_results": [],
}
_MAX_RESULTS = 100


def _push_result(row: dict[str, Any]) -> None:
    lst = _STATUS.get("last_results")
    if not isinstance(lst, list):
        lst = []
    lst.append(row)
    if len(lst) > _MAX_RESULTS:
        lst = lst[-_MAX_RESULTS:]
    _STATUS["last_results"] = lst


def enqueue_semantic_index_job(memory_id: str) -> dict[str, Any]:
    mid = str(memory_id or "").strip()
    if not mid:
        return {"status": "error", "detail": "missing_memory_id"}
    with _LOCK:
        if mid in _IN_QUEUE:
            return {"status": "ok", "enqueued": False, "reason": "already_pending", "pending": len(_QUEUE)}
        _QUEUE.append(mid)
        _IN_QUEUE.add(mid)
        _STATUS["pending"] = len(_QUEUE)
    return {"status": "ok", "enqueued": True, "pending": len(_QUEUE)}


def _pop_next() -> str | None:
    with _LOCK:
        if not _QUEUE:
            _STATUS["pending"] = 0
            return None
        mid = _QUEUE.popleft()
        _IN_QUEUE.discard(mid)
        _STATUS["pending"] = len(_QUEUE)
        return mid


def index_pending_memories(limit: int = 120) -> dict[str, Any]:
    started = time.time()
    processed = 0
    indexed = 0
    skipped = 0
    errors = 0
    faiss_ready = bool(fsm._faiss_available())  # type: ignore[attr-defined]
    while processed < max(1, int(limit)):
        mid = _pop_next()
        if not mid:
            break
        processed += 1
        if not faiss_ready:
            skipped += 1
            with _LOCK:
                _STATUS["skipped"] = int(_STATUS.get("skipped") or 0) + 1
                _push_result({"at": fm._now_iso(), "memory_id": mid, "status": "skipped", "reason": "faiss_unavailable"})  # noqa: SLF001
            continue
        entry = None
        for e in fm.entries_snapshot_for_tests():
            if str(e.get("id") or "") == mid:
                entry = e
                break
        if not entry:
            skipped += 1
            with _LOCK:
                _STATUS["skipped"] = int(_STATUS.get("skipped") or 0) + 1
                _push_result({"at": fm._now_iso(), "memory_id": mid, "status": "skipped", "reason": "not_found"})  # noqa: SLF001
            continue

        rep = fsm.add_memory_embedding(entry)
        st = str(rep.get("status") or "")
        if st == "ok" and rep.get("added") is True:
            indexed += 1
            with _LOCK:
                _STATUS["indexed"] = int(_STATUS.get("indexed") or 0) + 1
                _push_result({"at": fm._now_iso(), "memory_id": mid, "status": "indexed"})  # noqa: SLF001
        elif st == "ok":
            skipped += 1
            with _LOCK:
                _STATUS["skipped"] = int(_STATUS.get("skipped") or 0) + 1
                _push_result(
                    {
                        "at": fm._now_iso(),  # noqa: SLF001
                        "memory_id": mid,
                        "status": "skipped",
                        "reason": str(rep.get("reason") or "not_added"),
                    }
                )
        else:
            errors += 1
            with _LOCK:
                _STATUS["errors"] = int(_STATUS.get("errors") or 0) + 1
                _STATUS["last_error"] = str(rep.get("detail") or "index_error")
                _push_result(
                    {
                        "at": fm._now_iso(),  # noqa: SLF001
                        "memory_id": mid,
                        "status": "error",
                        "reason": str(rep.get("detail") or "index_error"),
                    }
                )

    with _LOCK:
        _STATUS["last_run_at"] = fm._now_iso()  # noqa: SLF001
        _STATUS["pending"] = len(_QUEUE)
    return {
        "status": "ok",
        "processed": processed,
        "indexed": indexed,
        "skipped": skipped,
        "errors": errors,
        "elapsed_ms": round((time.time() - started) * 1000.0, 2),
        "pending": len(_QUEUE),
    }


def process_semantic_index_queue() -> dict[str, Any]:
    return index_pending_memories(limit=120)


def get_semantic_worker_status() -> dict[str, Any]:
    with _LOCK:
        out = copy.deepcopy(_STATUS)
        out["pending"] = len(_QUEUE)
        out["queue_sample"] = list(_QUEUE)[:20]
        return out


def clear_semantic_queue_for_tests() -> dict[str, Any]:
    with _LOCK:
        _QUEUE.clear()
        _IN_QUEUE.clear()
        _STATUS.update(
            {
                "pending": 0,
                "indexed": 0,
                "skipped": 0,
                "errors": 0,
                "last_run_at": None,
                "last_error": "",
                "last_results": [],
            }
        )
    return {"status": "ok"}

