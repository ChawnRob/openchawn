from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

STORE_PATH = Path("data/memory/fractal_memory.json")
MAX_CONTEXT_MEMORIES = 5
_STORE_LOCK = Lock()

_SENSITIVE_RE = re.compile(
    r"(api[_-]?key|sk-[a-z0-9_-]{8,}|token|secret|password)",
    re.IGNORECASE,
)
_TAG_HINTS = (
    "openchawn",
    "provider",
    "railway",
    "memory",
    "security",
    "ui",
    "architecture",
)


@dataclass(frozen=True)
class MemoryWriteResult:
    saved: bool
    reason: str = ""
    entry_ids: tuple[str, ...] = ()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_entries() -> list[dict]:
    if not STORE_PATH.exists():
        return []
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _save_entries(entries: list[dict]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _contains_sensitive_text(*parts: str) -> bool:
    text = " ".join([(p or "") for p in parts])
    return bool(_SENSITIVE_RE.search(text))


def _detect_tags(*parts: str) -> list[str]:
    content = " ".join([(p or "") for p in parts]).lower()
    tags = [tag for tag in _TAG_HINTS if tag in content]
    return tags


def _summary_text(user_message: str, assistant_response: str) -> str:
    raw = f"Q: {(user_message or '').strip()} | R: {(assistant_response or '').strip()}"
    short = re.sub(r"\s+", " ", raw).strip()
    if len(short) <= 220:
        return short
    return short[:217].rstrip() + "..."


def _concept_summary(user_message: str, assistant_response: str, tags: list[str]) -> str:
    important = [t for t in tags if t in {"architecture", "security", "provider", "memory", "railway"}]
    if important:
        return f"Decision/Concept: {', '.join(sorted(set(important)))}"
    text = re.sub(r"\s+", " ", f"{user_message} {assistant_response}").strip()
    return f"Concept: {text[:120]}".rstrip()


def _importance_score(user_message: str, assistant_response: str, tags: list[str]) -> float:
    score = 0.45
    length_bonus = min(0.25, (len(user_message) + len(assistant_response)) / 4000.0)
    tag_bonus = min(0.20, len(tags) * 0.05)
    if any(t in tags for t in ("architecture", "security", "provider")):
        tag_bonus += 0.08
    return round(min(0.98, score + length_bonus + tag_bonus), 2)


def _mk_entry(
    *,
    source: str,
    user_message: str,
    assistant_response: str,
    summary: str,
    tags: list[str],
    importance_score: float,
    project: str,
    parent_id: str | None = None,
    children_ids: list[str] | None = None,
    memory_level: str = "raw_memory",
) -> dict:
    return {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "timestamp": _now_iso(),
        "source": source or "chat",
        "user_message": user_message,
        "assistant_response": assistant_response,
        "summary": summary,
        "tags": tags,
        "importance_score": importance_score,
        "project": project or "",
        "parent_id": parent_id,
        "children_ids": children_ids or [],
        "memory_level": memory_level,
    }


def write_exchange(
    *,
    source: str,
    user_message: str,
    assistant_response: str,
    project: str = "",
) -> MemoryWriteResult:
    if _contains_sensitive_text(user_message, assistant_response):
        return MemoryWriteResult(saved=False, reason="sensitive_content_detected")

    tags = _detect_tags(user_message, assistant_response, project)
    importance = _importance_score(user_message, assistant_response, tags)
    summary = _summary_text(user_message, assistant_response)

    raw_entry = _mk_entry(
        source=source,
        user_message=user_message,
        assistant_response=assistant_response,
        summary=summary,
        tags=tags,
        importance_score=importance,
        project=project,
        memory_level="raw_memory",
    )
    summary_entry = _mk_entry(
        source=source,
        user_message=user_message[:280],
        assistant_response="",
        summary=summary,
        tags=tags,
        importance_score=max(0.35, round(importance - 0.1, 2)),
        project=project,
        parent_id=raw_entry["id"],
        memory_level="summary_memory",
    )
    concept_entry = _mk_entry(
        source=source,
        user_message="",
        assistant_response="",
        summary=_concept_summary(user_message, assistant_response, tags),
        tags=sorted(set(tags + ["concept"])),
        importance_score=max(0.5, round(importance, 2)),
        project=project,
        parent_id=raw_entry["id"],
        memory_level="concept_memory",
    )
    raw_entry["children_ids"] = [summary_entry["id"], concept_entry["id"]]

    with _STORE_LOCK:
        entries = _load_entries()
        entries.extend([raw_entry, summary_entry, concept_entry])
        _save_entries(entries)

    return MemoryWriteResult(
        saved=True,
        entry_ids=(raw_entry["id"], summary_entry["id"], concept_entry["id"]),
    )


def _keywords(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-zA-Z0-9_]{3,}", (text or "").lower())}


def search_memories(query: str, limit: int = MAX_CONTEXT_MEMORIES) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    keys = _keywords(q)
    with _STORE_LOCK:
        entries = _load_entries()

    scored: list[tuple[float, dict]] = []
    for e in entries:
        bucket = " ".join(
            [
                str(e.get("user_message", "")),
                str(e.get("assistant_response", "")),
                str(e.get("summary", "")),
                " ".join([str(t) for t in e.get("tags", [])]),
                str(e.get("project", "")),
            ]
        ).lower()
        if not bucket:
            continue
        overlap = len(keys.intersection(_keywords(bucket)))
        if overlap == 0 and q.lower() not in bucket:
            continue
        score = float(overlap) + float(e.get("importance_score", 0.0))
        scored.append((score, e))

    scored.sort(key=lambda item: (item[0], item[1].get("timestamp", "")), reverse=True)
    return [e for _, e in scored[: max(1, min(limit, 10))]]


def build_memory_context(query: str, limit: int = MAX_CONTEXT_MEMORIES) -> tuple[str, list[dict]]:
    memories = search_memories(query, limit=limit)
    if not memories:
        return "", []
    lines = []
    for idx, mem in enumerate(memories, start=1):
        level = mem.get("memory_level", "raw_memory")
        summary = str(mem.get("summary", "")).strip()
        tags = ", ".join([str(t) for t in mem.get("tags", [])][:4])
        lines.append(f"{idx}. [{level}] {summary} | tags: {tags}")
    return "\n".join(lines), memories


def recent_memories(limit: int = 10) -> list[dict]:
    with _STORE_LOCK:
        entries = _load_entries()
    entries.sort(key=lambda e: str(e.get("timestamp", "")), reverse=True)
    return entries[: max(1, min(limit, 50))]


def memory_health() -> dict[str, object]:
    with _STORE_LOCK:
        entries = _load_entries()
    warning = ""
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
        warning = "local JSON memory is ephemeral on Railway"
    return {
        "memory_enabled": True,
        "memory_backend": "local_json",
        "entries_count": len(entries),
        "storage_path": str(STORE_PATH),
        "status": "ok",
        "warning": warning,
    }

