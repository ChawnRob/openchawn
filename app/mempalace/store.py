from __future__ import annotations
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from app.mempalace.schema import MemoryEntry, MemoryType, MemoryStatus

_PATH = Path(os.getenv("MEMPALACE_PATH", "data/mempalace/memories.json"))
_LOCK = threading.Lock()


# ─── Persistance JSON local-first ──────────────────────────────────────────

def _ensure_file() -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _PATH.exists():
        _PATH.write_text("[]", encoding="utf-8")


def load_memories() -> list[MemoryEntry]:
    _ensure_file()
    with _LOCK:
        with _PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    return [MemoryEntry.from_dict(r) for r in raw]


def save_memories(entries: list[MemoryEntry]) -> None:
    _ensure_file()
    tmp = _PATH.with_suffix(".tmp")
    data = [e.to_dict() for e in entries]
    with _LOCK:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(_PATH)


# ─── API publique ──────────────────────────────────────────────────────────

def add_memory(
    content: str,
    *,
    type: MemoryType = "fact",
    project: str = "openchawn",
    summary: str = "",
    importance_score: float = 0.5,
    confidence: float = 0.8,
    source: str = "user",
) -> MemoryEntry:
    entry = MemoryEntry(
        content=content,
        type=type,
        project=project,
        summary=summary,
        importance_score=importance_score,
        confidence=confidence,
        source=source,
    )
    mems = load_memories()
    mems.append(entry)
    save_memories(mems)
    return entry


def update_reuse_score(entry_id: str, increment: float = 1.0) -> Optional[MemoryEntry]:
    mems = load_memories()
    updated: Optional[MemoryEntry] = None
    for e in mems:
        if e.id == entry_id:
            e.reuse_score += increment
            e.last_used_at = datetime.utcnow().isoformat()
            updated = e
            break
    if updated:
        save_memories(mems)
    return updated


def set_status(entry_id: str, status: MemoryStatus) -> Optional[MemoryEntry]:
    mems = load_memories()
    for e in mems:
        if e.id == entry_id:
            e.status = status
            save_memories(mems)
            return e
    return None
