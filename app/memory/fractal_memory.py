from __future__ import annotations

import json
import logging
import os
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.settings import get_settings

STORE_PATH = Path("data/memory/fractal_memory.json")
MAX_CONTEXT_MEMORIES = 5
_STORE_LOCK = Lock()
logger = logging.getLogger("openchawn.memory.fractal")

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


class MemoryBackendConfigError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryBackend(ABC):
    name = "base"

    @abstractmethod
    def load_entries(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def save_entries(self, entries: list[dict]) -> None:
        raise NotImplementedError

    @abstractmethod
    def persistent_storage(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def storage_path(self) -> str:
        raise NotImplementedError

    def backend_warning(self) -> str:
        return ""

    def backend_status(self) -> str:
        return "ok"


class LocalJsonMemoryBackend(MemoryBackend):
    name = "json"

    def __init__(self, path: Path) -> None:
        self.path = path

    def load_entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    def save_entries(self, entries: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def persistent_storage(self) -> bool:
        # Railway filesystem is ephemeral across redeploys/restarts.
        return not (os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))

    def storage_path(self) -> str:
        return str(self.path)

    def backend_warning(self) -> str:
        if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
            return "local JSON memory is ephemeral on Railway"
        return ""


class PostgresMemoryBackend(MemoryBackend):
    name = "postgres"

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS fractal_memories (
        id TEXT PRIMARY KEY,
        timestamp TIMESTAMPTZ NOT NULL,
        source TEXT NOT NULL,
        user_message TEXT NOT NULL,
        assistant_response TEXT NOT NULL,
        summary TEXT NOT NULL,
        tags JSONB NOT NULL,
        importance_score DOUBLE PRECISION NOT NULL,
        project TEXT NOT NULL,
        parent_id TEXT NULL,
        children_ids JSONB NOT NULL,
        metadata JSONB NOT NULL
    );
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = (database_url or "").strip()
        if not self.database_url:
            raise MemoryBackendConfigError(
                "MEMORY_BACKEND=postgres requires DATABASE_URL (or MEMORY_DB_URL)."
            )

    def load_entries(self) -> list[dict]:
        # Prepared for future Railway persistent storage; no migration yet.
        logger.info("postgres memory backend selected (read path prepared, no migration executed yet)")
        return []

    def save_entries(self, entries: list[dict]) -> None:
        _ = entries
        logger.info("postgres memory backend selected (write path prepared, no migration executed yet)")

    def persistent_storage(self) -> bool:
        return True

    def storage_path(self) -> str:
        return "postgres://fractal_memories"

    def backend_status(self) -> str:
        return "prepared_not_migrated"


def _build_backend() -> MemoryBackend:
    s = get_settings()
    backend = (s.memory_backend or "json").strip().lower() or "json"
    if backend == "postgres":
        return PostgresMemoryBackend(database_url=s.memory_db_url)
    return LocalJsonMemoryBackend(STORE_PATH)


def _get_backend() -> MemoryBackend:
    try:
        return _build_backend()
    except MemoryBackendConfigError:
        raise
    except Exception as e:
        raise MemoryBackendConfigError(f"Memory backend initialization failed: {e}") from e


def _load_entries() -> list[dict]:
    backend = _get_backend()
    return backend.load_entries()


def _save_entries(entries: list[dict]) -> None:
    backend = _get_backend()
    backend.save_entries(entries)


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
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        logger.warning("memory write skipped reason=backend_config_error detail=%s", e)
        return MemoryWriteResult(saved=False, reason=str(e))

    if _contains_sensitive_text(user_message, assistant_response):
        logger.info("memory write skipped reason=sensitive_content_detected")
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
    logger.info(
        "memory write saved entries=%s project=%s source=%s",
        3,
        project or "",
        source or "chat",
    )

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
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        logger.warning("memory retrieval skipped reason=backend_config_error detail=%s", e)
        return []
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
    logger.info("memory retrieval query_len=%s count=%s", len(query or ""), len(memories))
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
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        logger.warning("memory recent skipped reason=backend_config_error detail=%s", e)
        return []
    with _STORE_LOCK:
        entries = _load_entries()
    entries.sort(key=lambda e: str(e.get("timestamp", "")), reverse=True)
    return entries[: max(1, min(limit, 50))]


def memory_health() -> dict[str, object]:
    settings = get_settings()
    backend_name = (settings.memory_backend or "json").strip().lower() or "json"
    persistent = False
    status = "ok"
    warning = ""
    config_error = ""
    entries: list[dict] = []
    storage = str(STORE_PATH)

    try:
        backend = _get_backend()
        backend_name = backend.name
        persistent = backend.persistent_storage()
        status = backend.backend_status()
        warning = backend.backend_warning()
        storage = backend.storage_path()
        with _STORE_LOCK:
            entries = backend.load_entries()
    except MemoryBackendConfigError as e:
        status = "error"
        config_error = str(e)
    except Exception as e:
        status = "error"
        config_error = f"memory health error: {e}"

    return {
        "memory_enabled": True,
        "memory_backend": backend_name,
        "persistent_storage": persistent,
        "railway_ephemeral_warning": warning,
        "entries_count": len(entries),
        "storage_path": storage,
        "status": status,
        "config_error": config_error,
    }

