from __future__ import annotations

import json
import logging
import math
import os
import re
import uuid
import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.settings import get_settings

STORE_PATH = Path("data/memory/fractal_memory.json")
MAX_CONTEXT_MEMORIES = 12  # couches agrégées (session+project+user+system réduites)
STORE_VERSION = 2
_STORE_LOCK = Lock()
_LAST_CONTEXT_LOCK = Lock()
logger = logging.getLogger("openchawn.memory.fractal")

# Dernier retrieval injecté (debug / introspection — best-effort multi-workers)
_FUTURE_OBS_UI_NOTE = (
    "Futur: timeline UI, memory graph UI, semantic explorer (non implémentés)."
)
_LAST_CONTEXT_SNAPSHOT: dict[str, object] = {
    "captured_at": None,
    "query_preview": "",
    "user_key_preview": "",
    "items": [],
    "note": _FUTURE_OBS_UI_NOTE,
}

_MAX_REINFORCEMENT_HISTORY = 40
_MAX_DECAY_HISTORY = 28

# Types mémoire multi-couches (V11.6)
MEMORY_TYPES = frozenset({"system", "project", "user", "session"})
KNOWN_PROJECT_SLUGS = frozenset(
    {"openchawn", "fluxorca", "weetao", "illhu", "luthor"}
)

# Métadonnées réservées (compat JSON existant + futur scheduler / LTM / retrieval sémantique)
MEMORY_DECAY_FIELDS = frozenset(
    {
        "archived_at",
        "decayed_at",
        "last_access_ts",
        "age_weight",
        # Prévu V11.6+ (non implémenté côté runtime)
        "memory_decay_scheduler",
        "long_term_memory",
        "semantic_retrieval",
        "semantic_vector_ref",
        "embedded_at",
    }
)

MEMORY_LIFECYCLE_ACTIVE = "active"
MEMORY_LIFECYCLE_ARCHIVED = "archived"
MEMORY_LIFECYCLE_STATUSES = frozenset({MEMORY_LIFECYCLE_ACTIVE, MEMORY_LIFECYCLE_ARCHIVED})

# Archivage : faible importance, ancien, jamais relu (ni raw ni summary ni concept)
_MIN_ARCHIVE_AGE_DAYS = 21
_MAX_ARCHIVE_IMPORTANCE = 0.34
_CONCEPT_MERGE_STOPWORDS = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "de",
        "du",
        "des",
        "est",
        "et",
        "ou",
        "en",
        "a",
        "à",
        "the",
        "son",
        "sa",
        "ses",
    }
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


def _parse_iso_ts(ts: str | None) -> datetime | None:
    if not (ts or "").strip():
        return None
    s = ts.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _memory_type_decay_weight(mt: str) -> float:
    return {"system": 0.22, "project": 0.55, "user": 0.72, "session": 1.0}.get(
        (mt or "session").strip().lower(),
        1.0,
    )


def _entry_age_days(entry: dict) -> float:
    base = (
        _parse_iso_ts(str(entry.get("created_at") or ""))
        or _parse_iso_ts(str(entry.get("timestamp") or ""))
    )
    if not base:
        return 0.0
    delta = datetime.now(timezone.utc) - base
    return max(0.0, delta.total_seconds() / 86400.0)


def recompute_decay_score(entry: dict) -> float:
    """Score 0–100 : plus élevé = mémoire moins prioritaire dans le classement."""
    mt = str(entry.get("memory_type", "session"))
    age_d = _entry_age_days(entry)
    acc = int(entry.get("access_count") or 0)
    imp = float(entry.get("importance_score") or 0.0)
    wt = _memory_type_decay_weight(mt)
    age_boost = min(92.0, age_d * wt * 1.65)
    use_relief = min(52.0, math.log1p(max(0, acc)) * 13.5)
    importance_relief = imp * 38.0
    if str(entry.get("lifecycle_status")) == MEMORY_LIFECYCLE_ARCHIVED:
        age_boost *= 1.08
    d = age_boost - use_relief - importance_relief
    return round(max(0.0, min(100.0, d)), 2)


def concept_merge_key(summary: str) -> str:
    words = re.findall(
        r"[a-zA-ZÀ-ÖØ-öø-ÿ0-9]{2,}",
        (summary or "").lower(),
        flags=re.UNICODE,
    )
    tokens = sorted(w for w in words if w not in _CONCEPT_MERGE_STOPWORDS)
    return "|".join(tokens) if tokens else re.sub(r"[^a-z0-9àâäéèêëîïôùûüç]+", "", (summary or "").lower())


def _find_canon_for_concept_merge(
    entries: list[dict],
    *,
    concept_summary: str,
    memory_type: str,
    project_name: str,
    user_id: str,
) -> dict | None:
    key = concept_merge_key(concept_summary)
    if not key:
        return None
    mtype = (memory_type or "").strip().lower()
    pn = _normalize_project_slug(project_name or "")
    uid = (user_id or "").strip()

    def _scope_ok(e: dict) -> bool:
        if mtype == "system":
            return True
        if mtype == "project":
            return _normalize_project_slug(str(e.get("project_name") or "")) == pn
        # user / session : même utilisateur
        if str(e.get("user_id", "")).strip() != uid:
            return False
        if mtype == "user":
            return True
        # session : même projet si renseigné
        ep = _normalize_project_slug(str(e.get("project_name") or ""))
        return not pn or not ep or ep == pn

    candidates: list[dict] = []
    for e in entries:
        if str(e.get("memory_level")) != "concept_memory":
            continue
        if str(e.get("memory_type")) != mtype:
            continue
        if str(e.get("lifecycle_status", MEMORY_LIFECYCLE_ACTIVE)) != MEMORY_LIFECYCLE_ACTIVE:
            continue
        if not _scope_ok(e):
            continue
        if concept_merge_key(str(e.get("summary", ""))) != key:
            continue
        candidates.append(e)
    if not candidates:
        return None
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def _created(x: dict) -> datetime:
        return _parse_iso_ts(str(x.get("created_at") or "")) or _parse_iso_ts(str(x.get("timestamp") or "")) or epoch

    candidates.sort(key=_created)
    return candidates[0]


def _concept_sentiment_signals(text: str) -> tuple[str | None, str | None]:
    """Retourne (sujet, polarité). Polarité forbid | allow."""
    lowered = (text or "").lower()
    subject = None
    if "ollama" in lowered:
        subject = "ollama"
    elif "deepseek" in lowered:
        subject = "deepseek"

    polarity = None
    if subject:
        if re.search(
            r"interdit|forbidden|désactivé|desactivé|désactiv|ban",
            lowered,
            re.IGNORECASE,
        ):
            polarity = "forbid"
        elif re.search(
            r"principal|défaut|defaut|production|prioritaire|priorite|prefer",
            lowered,
            re.IGNORECASE,
        ):
            polarity = "allow"
    return subject, polarity


def apply_provider_contradiction_flags(
    existing: list[dict],
    *,
    pivot_summary: str,
    new_entries: list[dict],
) -> bool:
    """Marque les entrées en contradiction (signaux simples). Ne résout rien."""
    ns, npol = _concept_sentiment_signals(pivot_summary)
    if not ns or not npol:
        return False
    conflict = False
    for e in existing:
        if str(e.get("memory_level")) != "concept_memory":
            continue
        if not is_active_memory(e):
            continue
        summ = str(e.get("summary", ""))
        os, opol = _concept_sentiment_signals(summ)
        if os != ns:
            continue
        if opol and npol and opol != npol:
            e["contradiction_detected"] = True
            conflict = True
    if conflict:
        for ne in new_entries:
            ne["contradiction_detected"] = True
    return conflict


def _metadata_append_capped(
    entry: dict,
    key: str,
    item: dict,
    cap: int,
) -> None:
    md = entry.setdefault("metadata", {})
    if not isinstance(md, dict):
        return
    hist = md.get(key)
    if not isinstance(hist, list):
        hist = []
    hist = list(hist)
    hist.append(item)
    md[key] = hist[-cap:]


def refresh_lifecycle_decay(entries: list[dict]) -> None:
    now = _now_iso()
    for e in entries:
        old = float(e.get("decay_score") or 0.0)
        new_v = recompute_decay_score(e)
        if abs(new_v - old) >= 0.35:
            _metadata_append_capped(
                e,
                "decay_history",
                {"at": now, "decay_score": new_v, "previous": old, "reason": "recompute"},
                _MAX_DECAY_HISTORY,
            )
        e["decay_score"] = new_v


def _attach_concept_canon_metadata(concept_entry: dict, summary_text: str) -> None:
    md = concept_entry.setdefault("metadata", {})
    if not isinstance(md, dict):
        return
    md.setdefault("aliases", [summary_text])
    md.setdefault("merge_count", 1)
    md.setdefault("last_seen", concept_entry.get("timestamp") or _now_iso())
    md.setdefault("concept_merge_key", concept_merge_key(summary_text))


def _increment_concept_canon_merge(canon: dict, merged_phrase: str) -> None:
    md = canon.setdefault("metadata", {})
    if not isinstance(md, dict):
        return
    base_summ = str(canon.get("summary", "")).strip()
    prev_aliases = md.get("aliases")
    aliases = list(prev_aliases) if isinstance(prev_aliases, list) else []
    if base_summ and base_summ not in aliases:
        aliases.insert(0, base_summ)
    merged = merged_phrase.strip()
    if merged and merged not in aliases:
        aliases.append(merged[:500])
    md["aliases"] = aliases
    md["merge_count"] = int(md.get("merge_count") or 1) + 1
    md["last_seen"] = _now_iso()


def apply_archive_rules(entries: list[dict]) -> int:
    """Archive les entrées bruit faible sans accès réel."""
    archived = 0
    now = _now_iso()
    for e in entries:
        if str(e.get("lifecycle_status")) == MEMORY_LIFECYCLE_ARCHIVED:
            continue
        uid = str(e.get("access_count") or 0).strip()
        try:
            acc = int(uid)
        except (TypeError, ValueError):
            acc = 0
        imp = float(e.get("importance_score") or 0.0)
        age = _entry_age_days(e)

        eligible = (
            acc == 0
            and age >= float(_MIN_ARCHIVE_AGE_DAYS)
            and imp <= _MAX_ARCHIVE_IMPORTANCE + 1e-9
            and float(e.get("decay_score", 50)) >= 38.0
        )
        if eligible:
            e["lifecycle_status"] = MEMORY_LIFECYCLE_ARCHIVED
            md = e.setdefault("metadata", {})
            if isinstance(md, dict):
                md.setdefault("archived_at", now)
            archived += 1
    return archived


def reinforce_entries(entries: list[dict], ids: Iterable[str]) -> None:
    want = {str(i) for i in ids if i}
    now = _now_iso()
    for e in entries:
        eid = str(e.get("id", ""))
        if eid not in want:
            continue
        if str(e.get("lifecycle_status", MEMORY_LIFECYCLE_ACTIVE)) != MEMORY_LIFECYCLE_ACTIVE:
            continue
        prev_decay = float(e.get("decay_score") or 0.0)
        e["access_count"] = int(e.get("access_count") or 0) + 1
        e["last_accessed_at"] = now
        imp = float(e.get("importance_score") or 0.0)
        reduction = 6.0 + imp * 18.0
        new_decay = round(max(0.0, prev_decay - reduction), 2)
        e["decay_score"] = new_decay
        md = e.setdefault("metadata", {})
        if isinstance(md, dict):
            md["retrieval_hits"] = int(e.get("access_count") or 0)
        _metadata_append_capped(
            e,
            "reinforcement_history",
            {
                "at": now,
                "decay_before": prev_decay,
                "decay_after": new_decay,
                "access_count_after": int(e.get("access_count") or 0),
            },
            _MAX_REINFORCEMENT_HISTORY,
        )
        if abs(new_decay - prev_decay) >= 0.2:
            _metadata_append_capped(
                e,
                "decay_history",
                {
                    "at": now,
                    "decay_score": new_decay,
                    "previous": prev_decay,
                    "reason": "reinforcement",
                },
                _MAX_DECAY_HISTORY,
            )


def is_active_memory(entry: dict) -> bool:
    return str(entry.get("lifecycle_status", MEMORY_LIFECYCLE_ACTIVE)) == MEMORY_LIFECYCLE_ACTIVE


def layered_sort_key(rel: int, importance: float, decay: float, ts: str) -> tuple[float, int, float, str]:
    """Décroissant : valeur composite forte d'abord (on trie reverse plus bas)."""
    composite = importance * 110.0 + float(rel) * 15.0 - decay * 0.85
    return composite, rel, importance, ts


def _composite_retrieval_score(rel: int, importance: float, decay: float) -> float:
    return importance * 110.0 + float(rel) * 15.0 - decay * 0.85


def _remember_last_context_snapshot(
    query: str,
    user_key: str,
    items_with_debug: list[dict],
) -> None:
    global _LAST_CONTEXT_SNAPSHOT
    sanitized: list[dict] = []
    for it in items_with_debug:
        dbg = it.get("_retrieval_debug")
        if not isinstance(dbg, dict):
            dbg = {}
        sanitized.append(
            {
                "memory_id": it.get("id"),
                "memory_type": it.get("memory_type"),
                "memory_level": it.get("memory_level"),
                "summary_preview": str(it.get("summary", ""))[:180],
                **dbg,
            }
        )
    with _LAST_CONTEXT_LOCK:
        _LAST_CONTEXT_SNAPSHOT = {
            "captured_at": _now_iso(),
            "query_preview": (query or "")[:320],
            "user_key_preview": (user_key or "")[:64],
            "items": sanitized,
            "note": _FUTURE_OBS_UI_NOTE,
        }


def get_last_memory_context() -> dict[str, object]:
    with _LAST_CONTEXT_LOCK:
        return copy.deepcopy(_LAST_CONTEXT_SNAPSHOT)

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
        "reserved_decay": {},  # futur: memory_decay_scheduler, LTM, semantic_retrieval
    }


def rebuild_logical_indexes(entries: list[dict]) -> dict[str, object]:
    system_concepts: list[str] = []
    project_concepts: dict[str, list[str]] = {}
    user_preferences: dict[str, list[str]] = {}
    for e in entries:
        if str(e.get("memory_level", "")) != "concept_memory":
            continue
        if not is_active_memory(e):
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
    ts_fallback = str(e.get("timestamp") or _now_iso())
    created = str(e.get("created_at") or "").strip() or ts_fallback
    e["created_at"] = created
    if not str(e.get("last_accessed_at") or "").strip():
        e["last_accessed_at"] = created
    try:
        e["access_count"] = max(0, int(e.get("access_count") or 0))
    except (TypeError, ValueError):
        e["access_count"] = 0
    st = str(e.get("lifecycle_status", MEMORY_LIFECYCLE_ACTIVE)).strip().lower()
    e["lifecycle_status"] = st if st in MEMORY_LIFECYCLE_STATUSES else MEMORY_LIFECYCLE_ACTIVE
    cd = e.get("contradiction_detected")
    if isinstance(cd, str):
        e["contradiction_detected"] = cd.strip().lower() in ("1", "true", "yes")
    else:
        e["contradiction_detected"] = bool(cd)
    try:
        ds = e.get("decay_score")
        if ds is None or ds == "":
            raise ValueError
        e["decay_score"] = float(ds)
    except (TypeError, ValueError):
        e["decay_score"] = recompute_decay_score(e)
    else:
        e["decay_score"] = round(max(0.0, min(100.0, float(e["decay_score"]))), 2)
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
        and is_active_memory(e)
    ]
    if not pool:
        pool = [
            e
            for e in entries
            if str(e.get("memory_type", "")) == memory_type and is_active_memory(e)
        ]

    scored: list[tuple[tuple[float, str], dict, int, float, str]] = []
    for e in pool:
        if memory_type == "session" and user_key:
            uid_e = str(e.get("user_id", "") or "").strip()
            if uid_e and uid_e != user_key:
                continue
        rel = _score_relevance(query_keys, e) if query_keys else 0
        imp = float(e.get("importance_score", 0.0))
        ts = str(e.get("timestamp", ""))
        decay = float(e.get("decay_score", 0.0))
        comp = layered_sort_key(rel, imp, decay, ts)[0]
        if prefer_recency:
            scored.append(((ts, comp), e, rel, imp, ts))
        else:
            scored.append(((comp, ts), e, rel, imp, ts))

    scored.sort(key=lambda x: x[0], reverse=True)

    out: list[dict] = []
    for _k, e, rel, imp, ts in scored:
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
        entries = [_ensure_entry_defaults(e) for e in entries]
        refresh_lifecycle_decay(entries)
        apply_archive_rules(entries)

        def _lines_for_label(label: str, items: list[dict]) -> str:
            if not items:
                return ""
            lines_l = [f"── {label} ──"]
            for it in items:
                summ = str(it.get("summary", "")).strip()
                if not summ:
                    continue
                lines_l.append(f"• {summ}")
            return "\n".join(lines_l)

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
                and is_active_memory(e)
            ],
            key=lambda x: (
                layered_sort_key(
                    0,
                    float(x.get("importance_score", 0.0)),
                    float(x.get("decay_score", 0.0)),
                    str(x.get("timestamp", "")),
                )[0],
                str(x.get("timestamp", "")),
            ),
            reverse=True,
        )[:2]
        if len(system_pick) < 2:
            for e in entries:
                if (
                    str(e.get("memory_type")) == "system"
                    and e not in system_pick
                    and is_active_memory(e)
                ):
                    system_pick.append(e)
                if len(system_pick) >= 2:
                    break

        seen_keys: set[str] = set()

        def _dedupe(lst: list[dict]) -> list[dict]:
            out_d: list[dict] = []
            for item in lst:
                k = _norm_summary_key(str(item.get("summary", "")))
                if k and k in seen_keys:
                    continue
                if k:
                    seen_keys.add(k)
                out_d.append(item)
            return out_d

        system_pick = _dedupe(system_pick)
        user_pick = _dedupe(user_pick)
        project_pick = _dedupe(project_pick)
        session_pick = _dedupe(session_pick)

        parts = [
            _lines_for_label("MÉMOIRE SYSTÈME (règles globales OpenChawn)", system_pick),
            _lines_for_label("PRÉFÉRENCES UTILISATEUR", user_pick),
            _lines_for_label("MÉMOIRE PROJET", project_pick),
            _lines_for_label("CONTEXTE SESSION (court terme)", session_pick),
        ]
        body = "\n\n".join(p for p in parts if p)

        def _annotate_layer(layer: str, picks: list[dict], *, prefer_recency: bool) -> list[dict]:
            out_a: list[dict] = []
            for i, src in enumerate(picks):
                rel = _score_relevance(keys, src) if layer != "system" else 0
                imp = float(src.get("importance_score", 0.0))
                decay = float(src.get("decay_score", 0.0))
                composite = _composite_retrieval_score(rel, imp, decay)
                if layer == "system":
                    why = "layer:system;strategy:importance_decay;deduped_pick"
                elif layer == "user":
                    why = "layer:user;keyword_overlap_with_query;user_scope"
                elif layer == "project":
                    why = "layer:project;keyword_overlap_with_query;project_scope"
                else:
                    why = "layer:session;keyword_overlap_with_query;session_user_scope"
                dbg: dict[str, object] = {
                    "why_selected": f"{why};layer_rank={i + 1};prefer_recency={prefer_recency}",
                    "relevance_score": rel,
                    "importance_score": imp,
                    "decay_score": decay,
                    "memory_type": str(src.get("memory_type", "")),
                    "retrieval_rank": 0,
                    "composite_score": round(composite, 2),
                }
                c = dict(src)
                c["_retrieval_debug"] = dbg
                out_a.append(c)
            return out_a

        sys_ex = _annotate_layer("system", system_pick, prefer_recency=False)
        usr_ex = _annotate_layer("user", user_pick, prefer_recency=False)
        proj_ex = _annotate_layer("project", project_pick, prefer_recency=False)
        sess_ex = _annotate_layer("session", session_pick, prefer_recency=True)
        all_mem: list[dict] = []
        rnk = 0
        for block in (sys_ex, usr_ex, proj_ex, sess_ex):
            for it in block:
                rnk += 1
                rd = it.get("_retrieval_debug")
                if isinstance(rd, dict):
                    rd["retrieval_rank"] = rnk
                all_mem.append(it)

        reinforced_ids = [str(it.get("id")) for it in all_mem if it.get("id")]
        reinforce_entries(entries, reinforced_ids)
        refresh_lifecycle_decay(entries)
        _save_entries(entries)

    _remember_last_context_snapshot(q, user_key, all_mem)

    logger.info(
        "layered memory counts system=%s user=%s project=%s session=%s query_len=%s",
        len(system_pick),
        len(user_pick),
        len(project_pick),
        len(session_pick),
        len(q),
    )
    return body, all_mem


def memories_by_type(
    memory_type: str,
    limit: int = 50,
    *,
    include_archived: bool = False,
) -> list[dict]:
    mt = (memory_type or "").strip().lower()
    if mt not in MEMORY_TYPES:
        return []
    try:
        _ = _get_backend()
    except MemoryBackendConfigError:
        return []
    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
        pool = [e for e in entries if str(e.get("memory_type")) == mt]
        if not include_archived:
            pool = [e for e in pool if is_active_memory(e)]
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

    # Colonnes futures alignées V11.6 lifecycle + observabilité (JSON metadata / hors schéma) :
    # created_at, last_accessed_at, access_count, decay_score, lifecycle_status, contradiction_detected
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
    now = _now_iso()
    meta: dict[str, object] = {}
    e = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "timestamp": now,
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
        "metadata": meta,
        "created_at": now,
        "last_accessed_at": now,
        "access_count": 0,
        "lifecycle_status": MEMORY_LIFECYCLE_ACTIVE,
        "contradiction_detected": False,
    }
    e["decay_score"] = recompute_decay_score(e)
    return e


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
    concept_summ = _concept_summary(user_message, assistant_response, tags)

    merged_into = False
    with _STORE_LOCK:
        entries = _load_entries()
        entries = [_ensure_entry_defaults(e) for e in entries]

        canon = _find_canon_for_concept_merge(
            entries,
            concept_summary=concept_summ,
            memory_type=mtype,
            project_name=proj_slug,
            user_id=uid,
        )

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

        if canon:
            merged_into = True
            _increment_concept_canon_merge(canon, concept_summ)
            canon["decay_score"] = round(max(0.0, float(canon.get("decay_score") or 0.0) - 5.5), 2)
            s_md = summary_entry.setdefault("metadata", {})
            if isinstance(s_md, dict):
                s_md["linked_concept_id"] = canon["id"]
                s_md["concept_merge"] = True
            raw_entry["children_ids"] = [summary_entry["id"]]
            bundle = [raw_entry, summary_entry]
            entry_ids: tuple[str, ...] = (raw_entry["id"], summary_entry["id"])
        else:
            concept_entry = _mk_entry(
                source=source,
                user_message="",
                assistant_response="",
                summary=concept_summ,
                tags=sorted(set(tags + ["concept"])),
                importance_score=max(0.5, round(importance, 2)),
                project=project or proj_slug,
                memory_type=mtype,
                project_name=proj_slug,
                user_id=uid,
                parent_id=raw_entry["id"],
                memory_level="concept_memory",
            )
            _attach_concept_canon_metadata(concept_entry, concept_summ)
            raw_entry["children_ids"] = [summary_entry["id"], concept_entry["id"]]
            bundle = [raw_entry, summary_entry, concept_entry]
            entry_ids = (raw_entry["id"], summary_entry["id"], concept_entry["id"])

        apply_provider_contradiction_flags(
            entries, pivot_summary=concept_summ, new_entries=bundle
        )
        entries.extend(bundle)
        refresh_lifecycle_decay(entries)
        apply_archive_rules(entries)
        _save_entries(entries)

    logger.info(
        "memory write saved entries=%s memory_type=%s project=%s user=%s source=%s merged=%s",
        len(bundle),
        mtype,
        proj_slug or "",
        "guest" if is_guest else (uid or "unknown"),
        source or "chat",
        merged_into,
    )

    return MemoryWriteResult(saved=True, entry_ids=entry_ids)


def _keywords(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-zA-Z0-9_]{3,}", (text or "").lower())}


def search_memories(
    query: str,
    limit: int = MAX_CONTEXT_MEMORIES,
    *,
    include_archived: bool = True,
) -> list[dict]:
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
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]

    scored: list[tuple[int, float, str, dict]] = []
    for e in entries:
        if not include_archived and not is_active_memory(e):
            continue
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


def top_memories(limit: int = 10, *, include_archived: bool = True) -> list[dict]:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        logger.warning("memory top skipped reason=backend_config_error detail=%s", e)
        return []
    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
    if not include_archived:
        entries = [e for e in entries if is_active_memory(e)]
    entries.sort(
        key=lambda e: (float(e.get("importance_score", 0.0)), str(e.get("timestamp", ""))),
        reverse=True,
    )
    return entries[: max(1, min(limit, 50))]


def concept_memories(limit: int = 20, *, include_archived: bool = True) -> list[dict]:
    tops = top_memories(limit=100, include_archived=include_archived)
    concepts = [m for m in tops if str(m.get("memory_level", "")) == "concept_memory"]
    return concepts[: max(1, min(limit, 50))]


def recent_memories(limit: int = 10, *, include_archived: bool = True) -> list[dict]:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        logger.warning("memory recent skipped reason=backend_config_error detail=%s", e)
        return []
    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
    if not include_archived:
        entries = [e for e in entries if is_active_memory(e)]
    entries.sort(key=lambda e: str(e.get("timestamp", "")), reverse=True)
    return entries[: max(1, min(limit, 50))]


def memory_observability_overview() -> dict[str, object]:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        return {"status": "error", "config_error": str(e)}
    lifecycle = memory_lifecycle_health()

    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
    active_memories = sum(1 for e in entries if is_active_memory(e))
    archived_memories = sum(
        1 for e in entries if str(e.get("lifecycle_status")) == MEMORY_LIFECYCLE_ARCHIVED
    )
    merged_concepts = 0
    for e in entries:
        if str(e.get("memory_level")) != "concept_memory":
            continue
        md = e.get("metadata")
        mc = int((md or {}).get("merge_count") or 1) if isinstance(md, dict) else 1
        if mc > 1:
            merged_concepts += 1

    contradiction_count = sum(1 for e in entries if e.get("contradiction_detected"))
    act = [e for e in entries if is_active_memory(e)]
    avg_imp = (
        round(sum(float(e.get("importance_score", 0.0)) for e in act) / len(act), 4)
        if act
        else None
    )
    avg_decay = (
        round(sum(float(e.get("decay_score", 0.0)) for e in act) / len(act), 4)
        if act
        else None
    )
    pj: dict[str, int] = {}
    for e in entries:
        p = _normalize_project_slug(str(e.get("project_name") or e.get("project") or "general"))
        key = p or "_none"
        pj[key] = pj.get(key, 0) + 1
    top_projects = [{"project": k, "count": v} for k, v in sorted(pj.items(), key=lambda kv: (-kv[1], kv[0]))[:12]]

    mt: dict[str, int] = {}
    for e in entries:
        t = str(e.get("memory_type") or "?")
        mt[t] = mt.get(t, 0) + 1
    top_memory_types = [{"memory_type": k, "count": v} for k, v in sorted(mt.items(), key=lambda kv: (-kv[1], kv[0]))]

    mh = lifecycle.get("memory_health_score")

    return {
        "status": "ok",
        "total_memories": len(entries),
        "active_memories": active_memories,
        "archived_memories": archived_memories,
        "contradiction_count": contradiction_count,
        "merged_concepts": merged_concepts,
        "average_importance": avg_imp,
        "average_decay": avg_decay,
        "memory_health_score": mh,
        "top_projects": top_projects,
        "top_memory_types": top_memory_types,
        "note": _FUTURE_OBS_UI_NOTE,
    }


def _lookup_entry(entries: list[dict], memory_id: str) -> dict | None:
    mid = (memory_id or "").strip()
    if not mid:
        return None
    for e in entries:
        if str(e.get("id")) == mid:
            return e
    return None


def memory_trace(memory_id: str) -> dict[str, object]:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        return {"status": "error", "config_error": str(e)}
    mid = (memory_id or "").strip()
    if not mid:
        return {"status": "not_found"}

    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
        e = _lookup_entry(entries, mid)

    if not e:
        return {"status": "not_found"}

    md_raw = e.get("metadata")
    md_dict: dict[str, object] = md_raw if isinstance(md_raw, dict) else {}

    rh = md_dict.get("reinforcement_history")
    reinforcement_history = rh if isinstance(rh, list) else []
    dh = md_dict.get("decay_history")
    decay_history = dh if isinstance(dh, list) else []

    aliases = md_dict.get("aliases")
    aliases_out = aliases if isinstance(aliases, list) else []

    linked_cc = md_dict.get("linked_concept_id")
    merged_into = None
    if linked_cc:
        merged_into = {"concept_id": str(linked_cc)}

    hits = md_dict.get("retrieval_hits")
    if hits is None:
        hits = int(e.get("access_count") or 0)

    return {
        "status": "ok",
        "memory_id": e.get("id"),
        "creation": {
            "created_at": e.get("created_at"),
            "timestamp": e.get("timestamp"),
            "source": e.get("source"),
            "memory_type": e.get("memory_type"),
            "memory_level": e.get("memory_level"),
            "project_name": e.get("project_name"),
            "user_id": e.get("user_id"),
            "parent_id": e.get("parent_id"),
        },
        "accesses": {
            "access_count": int(e.get("access_count") or 0),
            "last_accessed_at": e.get("last_accessed_at"),
        },
        "reinforcement_history": reinforcement_history,
        "decay_history": decay_history,
        "archive_status": str(e.get("lifecycle_status", MEMORY_LIFECYCLE_ACTIVE)),
        "contradiction_flags": {
            "contradiction_detected": bool(e.get("contradiction_detected")),
        },
        "merged_into": merged_into,
        "aliases": aliases_out,
        "retrieval_hits": hits,
        "importance_score": float(e.get("importance_score") or 0.0),
        "decay_score": float(e.get("decay_score") or 0.0),
        "note": _FUTURE_OBS_UI_NOTE,
    }


def concept_graph_lightweight() -> dict[str, object]:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        return {"status": "error", "config_error": str(e), "concepts": [], "note": _FUTURE_OBS_UI_NOTE}
    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
    concepts = [x for x in entries if str(x.get("memory_level")) == "concept_memory"]
    out_nodes: list[dict[str, object]] = []
    entry_by_id = {str(x.get("id")): x for x in entries if x.get("id")}

    for c in concepts:
        cid = str(c.get("id"))
        md = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        aliases = md.get("aliases") if isinstance(md.get("aliases"), list) else [str(c.get("summary") or "")]

        linked_memories: list[str] = []
        for x in entries:
            xm = x.get("metadata")
            if not isinstance(xm, dict):
                continue
            if str(xm.get("linked_concept_id") or "") == cid:
                xid = str(x.get("id") or "")
                if xid:
                    linked_memories.append(xid)
        for ch in c.get("children_ids") or []:
            s = str(ch)
            if s and s not in linked_memories:
                linked_memories.append(s)
        pid = c.get("parent_id")
        if pid:
            ps = str(pid)
            if ps and ps not in linked_memories:
                linked_memories.append(ps)

        projects: set[str] = set()
        pn_c = _normalize_project_slug(str(c.get("project_name") or ""))
        if pn_c:
            projects.add(pn_c)
        for lm in linked_memories:
            lx = entry_by_id.get(lm)
            if not lx:
                continue
            pnl = _normalize_project_slug(str(lx.get("project_name") or ""))
            if pnl:
                projects.add(pnl)

        contradiction_links: list[dict[str, object]] = []
        if bool(c.get("contradiction_detected")):
            subj_self, pol_self = _concept_sentiment_signals(str(c.get("summary", "")))
            for o in concepts:
                if o is c:
                    continue
                if not bool(o.get("contradiction_detected")):
                    continue
                sj, pj = _concept_sentiment_signals(str(o.get("summary", "")))
                if subj_self and sj == subj_self and pol_self and pj and pol_self != pj:
                    contradiction_links.append(
                        {
                            "other_concept_id": str(o.get("id")),
                            "subject": sj,
                            "relationship": "polarity_conflict_flagged",
                        }
                    )

        out_nodes.append(
            {
                "concept_id": cid,
                "summary": str(c.get("summary", ""))[:260],
                "aliases": aliases,
                "linked_projects": sorted(projects),
                "linked_memories": sorted(set(linked_memories)),
                "contradiction_links": contradiction_links,
            }
        )

    return {
        "status": "ok",
        "concept_count": len(out_nodes),
        "concepts": out_nodes,
        "note": _FUTURE_OBS_UI_NOTE,
    }


def list_archived_memories(
    *,
    project: str = "",
    memory_type: str = "",
    older_than_days: float | None = None,
    limit: int = 80,
) -> dict[str, object]:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        return {"status": "error", "config_error": str(e), "items": []}
    filt_mt = (memory_type or "").strip().lower()
    if filt_mt and filt_mt not in MEMORY_TYPES:
        return {"status": "error", "detail": "invalid_memory_type", "items": []}
    filt_proj = _normalize_project_slug(project or "")
    cap = max(1, min(int(limit), 150))

    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]
    arch = [e for e in entries if str(e.get("lifecycle_status")) == MEMORY_LIFECYCLE_ARCHIVED]

    out: list[dict] = []
    for e in arch:
        if filt_mt and str(e.get("memory_type")) != filt_mt:
            continue
        if filt_proj:
            ep = _normalize_project_slug(str(e.get("project_name") or ""))
            if ep != filt_proj:
                continue
        if older_than_days is not None:
            age = _entry_age_days(e)
            if age < float(older_than_days):
                continue
        out.append(e)

    out.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
    return {
        "status": "ok",
        "count": len(out),
        "items": out[:cap],
        "filters": {"project": project or None, "memory_type": filt_mt or None, "older_than_days": older_than_days},
        "note": _FUTURE_OBS_UI_NOTE,
    }


def memory_lifecycle_health() -> dict[str, object]:
    try:
        _ = _get_backend()
    except MemoryBackendConfigError as e:
        return {
            "status": "error",
            "config_error": str(e),
            "active_memories": 0,
            "archived_memories": 0,
            "merged_concepts": 0,
            "contradictions_detected": 0,
            "average_decay_score": None,
            "memory_health_score": None,
        }

    with _STORE_LOCK:
        entries = [_ensure_entry_defaults(e) for e in _load_entries()]

    active_memories = sum(1 for e in entries if is_active_memory(e))
    archived_memories = sum(
        1 for e in entries if str(e.get("lifecycle_status")) == MEMORY_LIFECYCLE_ARCHIVED
    )

    merged_concepts = 0
    for e in entries:
        if str(e.get("memory_level")) != "concept_memory":
            continue
        md = e.get("metadata")
        mc = int((md or {}).get("merge_count") or 1) if isinstance(md, dict) else 1
        if mc > 1:
            merged_concepts += 1

    contradictions_detected = sum(1 for e in entries if e.get("contradiction_detected"))

    decay_vals = [float(e.get("decay_score") or 0.0) for e in entries if is_active_memory(e)]
    average_decay_score = (
        round(sum(decay_vals) / len(decay_vals), 2) if decay_vals else None
    )

    pen_arch = min(28.0, archived_memories * 0.2)
    pen_contrad = min(30.0, contradictions_detected * 11.5)
    base = average_decay_score or 0.0
    memory_health_score = round(
        max(0.0, min(100.0, 100.0 - base * 0.62 - pen_arch - pen_contrad)),
        1,
    )

    return {
        "status": "ok",
        "active_memories": active_memories,
        "archived_memories": archived_memories,
        "merged_concepts": merged_concepts,
        "contradictions_detected": contradictions_detected,
        "average_decay_score": average_decay_score,
        "memory_health_score": memory_health_score,
    }


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

