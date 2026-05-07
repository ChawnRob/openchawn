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
MAX_CONTEXT_MEMORIES = 12  # couches agrégées (session+project+user+system réduites)
STORE_VERSION = 2
_STORE_LOCK = Lock()
logger = logging.getLogger("openchawn.memory.fractal")

# Types mémoire multi-couches (V11.6)
MEMORY_TYPES = frozenset({"system", "project", "user", "session"})
KNOWN_PROJECT_SLUGS = frozenset(
    {"openchawn", "fluxorca", "weetao", "illhu", "luthor"}
)

# Futur memory_decay / archival / aging — données réservées, non utilisées encore
MEMORY_DECAY_FIELDS = frozenset(
    {"archived_at", "decayed_at", "last_access_ts", "age_weight"}
)

# Indexes logiques séparés (concepts / préférences) — synchro depuis les entrées
DEFAULT_INDEXES: dict[str, object] = {
    "system_concepts": [],
    "project_concepts": {},  # project_slug -> list[str]
    "user_preferences": {},  # user_key -> list[str]
}

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
_PROJECT_KEYWORDS = {
    "openchawn",
    "provider",
    "providers",
    "railway",
    "memory",
    "security",
    "architecture",
    "deepseek",
    "kimi",
    "openai",
    "infomaniak",
    "ollama",
}


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

    def _read_document(self) -> tuple[list[dict], dict[str, object]]:
        if not self.path.exists():
            return [], dict(DEFAULT_INDEXES)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            return [], dict(DEFAULT_INDEXES)
        entries, indexes = parse_store_document_body(data)
        return entries, indexes

    def load_entries(self) -> list[dict]:
        entries, _indexes = self._read_document()
        return entries

    def save_entries(self, entries: list[dict]) -> None:
        indexes = rebuild_logical_indexes(entries)
        doc = serialize_store_document(entries, indexes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    def persistent_storage(self) -> bool:
        return not (os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))

    def storage_path(self) -> str:
        return str(self.path)

    def backend_warning(self) -> str:
        if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
            return "local JSON memory is ephemeral on Railway"
        return ""


def parse_store_document_body(data: object) -> tuple[list[dict], dict[str, object]]:
    """Retourne (entries normalisées, indexes depuis fichier ou reconstruction)."""
    if isinstance(data, list):
        entries = [_ensure_entry_defaults(e) for e in data if isinstance(e, dict)]
        return entries, rebuild_logical_indexes(entries)
    if isinstance(data, dict):
        entries_raw = data.get("entries")
        if isinstance(entries_raw, list):
            entries = [_ensure_entry_defaults(e) for e in entries_raw if isinstance(e, dict)]
            indexes = {
                "system_concepts": data.get("system_concepts") or [],
                "project_concepts": data.get("project_concepts") or {},
                "user_preferences": data.get("user_preferences") or {},
            }
            if (
                not indexes["system_concepts"]
                and not indexes["project_concepts"]
                and not indexes["user_preferences"]
            ):
                indexes = rebuild_logical_indexes(entries)
            return entries, indexes
    return [], dict(DEFAULT_INDEXES)


def serialize_store_document(entries: list[dict], indexes: dict[str, object]) -> dict[str, object]:
    return {
        "version": STORE_VERSION,
        "entries": entries,
        "system_concepts": list(indexes.get("system_concepts", [])),
        "project_concepts": dict(indexes.get("project_concepts", {})),
        "user_preferences": dict(indexes.get("user_preferences", {})),
        "reserved_decay": {},  # futur decay / archival
    }


def rebuild_logical_indexes(entries: list[dict]) -> dict[str, object]:
    system_concepts: list[str] = []
    project_concepts: dict[str, list[str]] = {}
    user_preferences: dict[str, list[str]] = {}
    for e in entries:
        if str(e.get("memory_level", "")) != "concept_memory":
            continue
        summary = str(e.get("summary", "")).strip()
        if not summary:
            continue
        mt = str(e.get("memory_type", "session"))
        if mt == "system":
            if summary not in system_concepts:
                system_concepts.append(summary)
            continue
        if mt == "project":
            slug = str(e.get("project_name") or e.get("project") or "general").strip().lower()
            lst = project_concepts.setdefault(slug, [])
            if summary not in lst:
                lst.append(summary)
            continue
        if mt == "user":
            uk = str(e.get("user_id") or "_anon").strip()
            lst = user_preferences.setdefault(uk, [])
            if summary not in lst:
                lst.append(summary)
    return {
        "system_concepts": system_concepts,
        "project_concepts": project_concepts,
        "user_preferences": user_preferences,
    }


def _normalize_project_slug(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^\w\d]+", "_", s)
    return s.strip("_")


def detect_project_slug_from_text(text: str) -> str:
    lowered = (text or "").lower()
    for slug in KNOWN_PROJECT_SLUGS:
        if slug in lowered.replace(" ", "").replace("-", "").replace("/", ""):
            return slug
    for slug in KNOWN_PROJECT_SLUGS:
        if slug in lowered:
            return slug
    return ""


def _ensure_entry_defaults(e: dict) -> dict:
    if "memory_type" not in e or str(e["memory_type"]) not in MEMORY_TYPES:
        inferred = _infer_legacy_memory_type(e)
        e["memory_type"] = inferred
    e["memory_type"] = str(e["memory_type"]).strip().lower()
    if "project_name" not in e or not str(e.get("project_name", "")).strip():
        e["project_name"] = _normalize_project_slug(str(e.get("project", "")))
    if "user_id" not in e:
        e["user_id"] = ""
    if "metadata" not in e or not isinstance(e.get("metadata"), dict):
        e["metadata"] = {}
    for k in MEMORY_DECAY_FIELDS:
        e["metadata"].setdefault(k, None)
    if "project" not in e:
        e["project"] = e.get("project_name", "")
    return e


def _infer_legacy_memory_type(e: dict) -> str:
    tags = [str(t).lower() for t in e.get("tags", [])]
    if "concept" in tags and str(e.get("summary", "")).startswith("Decision/Concept:"):
        return "project"
    return "session"


def classify_memory_type(
    *,
    user_message: str,
    assistant_response: str,
    project_name_hint: str,
    user_key: str,
    is_guest: bool,
) -> str:
    text = f"{user_message} {assistant_response}".lower()
    if re.search(
        r"(deepseek.*(principal|par défaut|defaut)|provider principal|"
        r"ollama.*(interdit|forbidden|désactivé)|railway.*(production|prod)|"
        r"mémoire système|memoire systeme)",
        text,
        re.IGNORECASE,
    ):
        return "system"
    if user_key and not is_guest and _looks_user_preference(user_message):
        return "user"
    if _normalize_project_slug(project_name_hint) or detect_project_slug_from_text(user_message):
        return "project"
    return "session"


def _looks_user_preference(msg: str) -> bool:
    m = (msg or "").lower()
    return any(
        k in m
        for k in (
            "préfère",
            "prefere",
            "préférence",
            "preference",
            "style",
            "ton ",
            "toujours",
            "réponses structurées",
            "reponses structurees",
            "comme bytebytego",
            "ingénieur",
            "ingenieur",
        )
    )


def _norm_summary_key(summary: str) -> str:
    return re.sub(r"\s+", " ", (summary or "").strip().lower())[:120]


def _score_relevance(keys: set[str], entry: dict) -> int:
    bucket = " ".join(
        [
            str(entry.get("user_message", "")),
            str(entry.get("assistant_response", "")),
            str(entry.get("summary", "")),
            " ".join(str(t) for t in entry.get("tags", [])),
            str(entry.get("project_name", "")),
            str(entry.get("project", "")),
        ]
    ).lower()
    if not bucket:
        return 0
    return len(keys.intersection(_keywords(bucket))) if keys else 0


def _pick_layer_entries(
    entries: list[dict],
    *,
    memory_type: str,
    query_keys: set[str],
    user_key: str,
    project_slug: str,
    limit: int,
    prefer_recency: bool,
) -> list[dict]:
    pool = [
        e
        for e in entries
        if str(e.get("memory_type", "")) == memory_type
        and str(e.get("memory_level", "")) in ("summary_memory", "concept_memory")
    ]
    if not pool:
        pool = [e for e in entries if str(e.get("memory_type", "")) == memory_type]

    scored: list[tuple[int, float, str, dict]] = []
    for e in pool:
        if memory_type == "session" and user_key:
            uid_e = str(e.get("user_id", "") or "").strip()
            if uid_e and uid_e != user_key:
                continue
        rel = _score_relevance(query_keys, e) if query_keys else 0
        imp = float(e.get("importance_score", 0.0))
        ts = str(e.get("timestamp", ""))
        scored.append((rel, imp, ts, e))

    if prefer_recency:
        scored.sort(key=lambda x: (x[2], x[0], x[1]), reverse=True)
    else:
        scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    out: list[dict] = []
    for rel, imp, ts, e in scored:
        if memory_type == "user" and user_key and str(e.get("user_id", "")) != user_key:
            continue
        if memory_type == "project" and project_slug:
            ep = str(e.get("project_name") or e.get("project") or "").lower()
            if ep and ep != project_slug and project_slug not in ep:
                if rel == 0:
                    continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


def build_layered_memory_context(
    query: str,
    *,
    user_key: str = "",
    project_name_hint: str = "",
    is_guest: bool = True,
) -> tuple[str, list[dict]]:
    q = (query or "").strip()
    keys = _keywords(q)
    project_slug = _normalize_project_slug(project_name_hint) or detect_project_slug_from_text(q)

    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        logger.warning("layered memory skipped reason=backend_config_error detail=%s", e)
        return "", []

    with _STORE_LOCK:
        entries = _load_entries()

    session_pick = _pick_layer_entries(
        entries,
        memory_type="session",
        query_keys=keys,
        user_key=user_key,
        project_slug=project_slug,
        limit=5,
        prefer_recency=True,
    )
    project_pick = _pick_layer_entries(
        entries,
        memory_type="project",
        query_keys=keys,
        user_key=user_key,
        project_slug=project_slug,
        limit=3,
        prefer_recency=False,
    )
    user_pick: list[dict] = []
    if user_key and not is_guest:
        user_pick = _pick_layer_entries(
            entries,
            memory_type="user",
            query_keys=keys,
            user_key=user_key,
            project_slug=project_slug,
            limit=2,
            prefer_recency=False,
        )

    system_pick = sorted(
        [
            e
            for e in entries
            if str(e.get("memory_type")) == "system"
            and str(e.get("memory_level", "")) in ("summary_memory", "concept_memory")
        ],
        key=lambda x: (float(x.get("importance_score", 0.0)), str(x.get("timestamp", ""))),
        reverse=True,
    )[:2]
    if len(system_pick) < 2:
        for e in entries:
            if str(e.get("memory_type")) == "system" and e not in system_pick:
                system_pick.append(e)
            if len(system_pick) >= 2:
                break

    seen_keys: set[str] = set()

    def _dedupe(lst: list[dict]) -> list[dict]:
        out: list[dict] = []
        for item in lst:
            k = _norm_summary_key(str(item.get("summary", "")))
            if k and k in seen_keys:
                continue
            if k:
                seen_keys.add(k)
            out.append(item)
        return out

    system_pick = _dedupe(system_pick)
    user_pick = _dedupe(user_pick)
    project_pick = _dedupe(project_pick)
    session_pick = _dedupe(session_pick)

    def _lines(label: str, items: list[dict]) -> str:
        if not items:
            return ""
        lines = [f"── {label} ──"]
        for it in items:
            summ = str(it.get("summary", "")).strip()
            if not summ:
                continue
            lines.append(f"• {summ}")
        return "\n".join(lines)

    parts = [
        _lines("MÉMOIRE SYSTÈME (règles globales OpenChawn)", system_pick),
        _lines("PRÉFÉRENCES UTILISATEUR", user_pick),
        _lines("MÉMOIRE PROJET", project_pick),
        _lines("CONTEXTE SESSION (court terme)", session_pick),
    ]
    body = "\n\n".join(p for p in parts if p)
    all_mem = system_pick + user_pick + project_pick + session_pick
    logger.info(
        "layered memory counts system=%s user=%s project=%s session=%s query_len=%s",
        len(system_pick),
        len(user_pick),
        len(project_pick),
        len(session_pick),
        len(q),
    )
    return body, all_mem


def memories_by_type(memory_type: str, limit: int = 50) -> list[dict]:
    mt = (memory_type or "").strip().lower()
    if mt not in MEMORY_TYPES:
        return []
    try:
        _ = _get_backend()
    except MemoryBackendConfigError:
        return []
    with _STORE_LOCK:
        entries = _load_entries()
    pool = [e for e in entries if str(e.get("memory_type")) == mt]
    pool.sort(key=lambda e: str(e.get("timestamp", "")), reverse=True)
    return pool[: max(1, min(limit, 200))]


def store_indexes_snapshot() -> dict[str, object]:
    try:
        entries = _load_entries()
    except MemoryBackendConfigError:
        return dict(DEFAULT_INDEXES)
    return rebuild_logical_indexes(entries)


class PostgresMemoryBackend(MemoryBackend):
    name = "postgres"

    # Colonnes futures alignées V11.6 (migration à activer avec DATABASE_URL)
    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS fractal_memories (
        id TEXT PRIMARY KEY,
        timestamp TIMESTAMPTZ NOT NULL,
        memory_type TEXT NOT NULL DEFAULT 'session',
        project_name TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
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
    uq = re.sub(r"\s+", " ", (user_message or "").strip())
    ar = re.sub(r"\s+", " ", (assistant_response or "").strip())
    first = f"Demande: {uq[:110]}".rstrip(" .,;:")
    second = f"Action: {ar[:110]}".rstrip(" .,;:")
    summary = f"{first}. {second}."
    return summary[:240].rstrip()


def _concept_summary(user_message: str, assistant_response: str, tags: list[str]) -> str:
    merged = f"{user_message} {assistant_response}".lower()
    if "deepseek" in merged and ("default" in merged or "par défaut" in merged or "principal" in merged):
        return "DeepSeek est provider principal"
    if "railway" in merged and ("production" in merged or "prod" in merged):
        return "Railway = backend production"
    if "ollama" in merged and any(x in merged for x in ("interdit", "disabled", "désactivé", "forbidden")):
        return "Ollama interdit production"

    important = [t for t in tags if t in {"architecture", "security", "provider", "memory", "railway"}]
    if important:
        return f"Decision/Concept: {', '.join(sorted(set(important)))}"
    text = re.sub(r"\s+", " ", f"{user_message} {assistant_response}").strip()
    return f"Concept: {text[:120]}".rstrip()


def _importance_score(user_message: str, assistant_response: str, tags: list[str]) -> float:
    text = f"{user_message} {assistant_response}".lower()
    words = _keywords(text)
    score = 0.20

    project_hits = len(words.intersection(_PROJECT_KEYWORDS))
    score += min(0.30, project_hits * 0.05)

    if any(k in text for k in ("decision", "choix", "adopter", "utiliser", "standard")):
        score += 0.12
    if any(k in text for k in ("architecture", "pattern", "orchestration", "routing")):
        score += 0.14
    if any(k in text for k in ("security", "sécurité", "secret", "token", "api key")):
        score += 0.16
    if any(k in text for k in ("provider", "deepseek", "kimi", "openai", "infomaniak")):
        score += 0.14
    if any(k in text for k in ("memory", "memoire", "mémoire")):
        score += 0.10
    if "railway" in text:
        score += 0.12
    if "openchawn" in text:
        score += 0.10

    tag_bonus = min(0.10, len(tags) * 0.02)
    score += tag_bonus
    return round(max(0.0, min(1.0, score)), 2)


def _mk_entry(
    *,
    source: str,
    user_message: str,
    assistant_response: str,
    summary: str,
    tags: list[str],
    importance_score: float,
    project: str,
    memory_type: str,
    project_name: str,
    user_id: str,
    parent_id: str | None = None,
    children_ids: list[str] | None = None,
    memory_level: str = "raw_memory",
) -> dict:
    slug = _normalize_project_slug(project_name or project)
    return {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "timestamp": _now_iso(),
        "memory_type": memory_type,
        "project_name": slug,
        "user_id": user_id or "",
        "source": source or "chat",
        "user_message": user_message,
        "assistant_response": assistant_response,
        "summary": summary,
        "tags": tags,
        "importance_score": importance_score,
        "project": project or slug or "",
        "parent_id": parent_id,
        "children_ids": children_ids or [],
        "memory_level": memory_level,
        "metadata": {},
    }


def write_exchange(
    *,
    source: str,
    user_message: str,
    assistant_response: str,
    project: str = "",
    user_key: str = "",
    project_name_hint: str = "",
    is_guest: bool = True,
) -> MemoryWriteResult:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        logger.warning("memory write skipped reason=backend_config_error detail=%s", e)
        return MemoryWriteResult(saved=False, reason=str(e))

    if _contains_sensitive_text(user_message, assistant_response):
        logger.info("memory write skipped reason=sensitive_content_detected")
        return MemoryWriteResult(saved=False, reason="sensitive_content_detected")

    hint = project_name_hint or project
    mtype = classify_memory_type(
        user_message=user_message,
        assistant_response=assistant_response,
        project_name_hint=hint,
        user_key=user_key,
        is_guest=is_guest,
    )
    proj_slug = _normalize_project_slug(hint) or detect_project_slug_from_text(
        f"{user_message} {assistant_response}"
    )
    uid = user_key or ""

    tags = _detect_tags(user_message, assistant_response, project or hint)
    importance = _importance_score(user_message, assistant_response, tags)
    if mtype == "system":
        importance = max(importance, 0.85)
    summary = _summary_text(user_message, assistant_response)

    raw_entry = _mk_entry(
        source=source,
        user_message=user_message,
        assistant_response=assistant_response,
        summary=summary,
        tags=tags,
        importance_score=importance,
        project=project or proj_slug,
        memory_type=mtype,
        project_name=proj_slug,
        user_id=uid,
        memory_level="raw_memory",
    )
    summary_entry = _mk_entry(
        source=source,
        user_message=user_message[:280],
        assistant_response="",
        summary=summary,
        tags=tags,
        importance_score=max(0.35, round(importance - 0.1, 2)),
        project=project or proj_slug,
        memory_type=mtype,
        project_name=proj_slug,
        user_id=uid,
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
        project=project or proj_slug,
        memory_type=mtype,
        project_name=proj_slug,
        user_id=uid,
        parent_id=raw_entry["id"],
        memory_level="concept_memory",
    )
    raw_entry["children_ids"] = [summary_entry["id"], concept_entry["id"]]

    with _STORE_LOCK:
        entries = _load_entries()
        entries.extend([raw_entry, summary_entry, concept_entry])
        _save_entries(entries)
    logger.info(
        "memory write saved entries=%s memory_type=%s project=%s user=%s source=%s",
        3,
        mtype,
        proj_slug or "",
        "guest" if is_guest else (uid or "unknown"),
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

    scored: list[tuple[int, float, str, dict]] = []
    for e in entries:
        bucket = " ".join(
            [
                str(e.get("user_message", "")),
                str(e.get("assistant_response", "")),
                str(e.get("summary", "")),
                " ".join([str(t) for t in e.get("tags", [])]),
                str(e.get("project", "")),
                str(e.get("project_name", "")),
                str(e.get("memory_type", "")),
            ]
        ).lower()
        if not bucket:
            continue
        overlap = len(keys.intersection(_keywords(bucket)))
        if overlap == 0 and q.lower() not in bucket:
            continue
        relevance = overlap if overlap > 0 else (1 if q.lower() in bucket else 0)
        importance = float(e.get("importance_score", 0.0))
        timestamp = str(e.get("timestamp", ""))
        scored.append((relevance, importance, timestamp, e))

    # ranking: pertinence -> importance -> recence
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [e for _, _, _, e in scored[: max(1, min(limit, 10))]]


def build_memory_context(query: str, limit: int = MAX_CONTEXT_MEMORIES) -> tuple[str, list[dict]]:
    ctx, memories = build_layered_memory_context(
        query,
        user_key="",
        project_name_hint="",
        is_guest=True,
    )
    if limit and len(memories) > limit:
        memories = memories[:limit]
    logger.info(
        "memory retrieval query_len=%s count=%s layered=fallback_anon",
        len((query or "").strip()),
        len(memories),
    )
    return ctx, memories


def top_memories(limit: int = 10) -> list[dict]:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        logger.warning("memory top skipped reason=backend_config_error detail=%s", e)
        return []
    with _STORE_LOCK:
        entries = _load_entries()
    entries.sort(
        key=lambda e: (float(e.get("importance_score", 0.0)), str(e.get("timestamp", ""))),
        reverse=True,
    )
    return entries[: max(1, min(limit, 50))]


def concept_memories(limit: int = 20) -> list[dict]:
    tops = top_memories(limit=100)
    concepts = [m for m in tops if str(m.get("memory_level", "")) == "concept_memory"]
    return concepts[: max(1, min(limit, 50))]


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

