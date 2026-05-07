"""
Timeline mémoire fractale V11.6 — événements légers (MVP JSON).
Futur : table Postgres append-only (même schéma logique).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

TIMELINE_VERSION = 1
TIMELINE_JSON_PATH = Path("data/memory/memory_timeline.json")
_MAX_TIMELINE_EVENTS = 12000
_TIMELINE_LOCK = Lock()

logger = logging.getLogger("openchawn.memory.timeline")

TIMELINE_EVENT_TYPES = frozenset(
    {
        "memory_created",
        "memory_retrieved",
        "memory_reinforced",
        "memory_archived",
        "concept_created",
        "concept_merged",
        "contradiction_detected",
        "context_injected",
    }
)

_SECRET_SNIP = re.compile(
    r"(api[_-]?key|sk-[a-z0-9_-]{8,}|token|secret|password)\s*[=:]\s*\S+",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_timeline_text(text: str, max_len: int = 480) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    if _SECRET_SNIP.search(s) or re.search(r"sk-[a-zA-Z0-9_-]{8,}", s):
        return "[REDACTED_SECRET]"
    return s[:max_len]


def _session_fallback(user_key: str) -> str:
    uk = (user_key or "").strip()
    return uk if uk else "anon"


def append_timeline_event(
    *,
    event_type: str,
    memory_id: str = "",
    memory_type: str = "",
    project_name: str = "",
    summary: str = "",
    importance_score: float = 0.0,
    decay_score: float = 0.0,
    lifecycle_status: str = "active",
    concept_ids: list[str] | None = None,
    contradiction_detected: bool = False,
    metadata: dict[str, object] | None = None,
    user_key: str = "",
    session_id: str = "",
) -> None:
    if event_type not in TIMELINE_EVENT_TYPES:
        logger.warning("timeline skip unknown event_type=%s", event_type)
        return
    try:
        meta = dict(metadata or {})
        uk = (user_key or "").strip() or "anon"
        sid = (session_id or "").strip() or str(meta.get("session_id") or "").strip()
        if not sid:
            sid = _session_fallback(user_key)
        meta["session_id"] = sid
        meta.setdefault("user_key", uk)

        ev: dict[str, object] = {
            "event_id": f"evt_{uuid.uuid4().hex[:16]}",
            "timestamp": _now_iso(),
            "event_type": event_type,
            "memory_id": memory_id or "",
            "memory_type": memory_type or "",
            "project_name": project_name or "",
            "summary": sanitize_timeline_text(summary),
            "importance_score": round(float(importance_score), 4),
            "decay_score": round(float(decay_score), 4),
            "lifecycle_status": lifecycle_status or "active",
            "concept_ids": list(concept_ids or []),
            "contradiction_detected": bool(contradiction_detected),
            "metadata": meta,
        }

        with _TIMELINE_LOCK:
            doc = _read_timeline_document_unlocked()
            events = list(doc.get("events") or [])
            events.append(ev)
            if len(events) > _MAX_TIMELINE_EVENTS:
                events = events[-_MAX_TIMELINE_EVENTS:]
            doc["events"] = events
            doc["version"] = TIMELINE_VERSION
            doc["updated_at"] = _now_iso()
            _write_timeline_document_unlocked(doc)
    except Exception as e:
        logger.warning("timeline append failed type=%s err=%s", event_type, e)


def _read_timeline_document_unlocked() -> dict[str, object]:
    p = TIMELINE_JSON_PATH
    if not p.exists():
        return {"version": TIMELINE_VERSION, "events": [], "note": "MVP timeline JSON"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {"version": TIMELINE_VERSION, "events": [], "note": "MVP timeline JSON"}


def _write_timeline_document_unlocked(doc: dict[str, object]) -> None:
    TIMELINE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    TIMELINE_JSON_PATH.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_timeline_events() -> list[dict]:
    with _TIMELINE_LOCK:
        doc = _read_timeline_document_unlocked()
        return list(doc.get("events") or [])  # shallow copy wrapper


def _parse_iso_boundary(s: str | None) -> str | None:
    if not (s or "").strip():
        return None
    t = str(s).strip()
    try:
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        dt = datetime.fromisoformat(t)
        return dt.isoformat()
    except (ValueError, TypeError, OSError):
        return None


def filter_timeline_events(
    *,
    project: str = "",
    memory_type: str = "",
    event_type: str = "",
    session_id: str = "",
    user_key: str = "",
    since: str | None = None,
    until: str | None = None,
    limit: int = 200,
) -> list[dict]:
    items = load_timeline_events()
    filt_mt = (memory_type or "").strip().lower()
    filt_et = (event_type or "").strip()
    filt_proj = (project or "").strip().lower()
    filt_sess = (session_id or "").strip()
    filt_uk = (user_key or "").strip()
    s_bound = _parse_iso_boundary(since)
    u_bound = _parse_iso_boundary(until)

    out: list[dict] = []
    for ev in items:
        if not isinstance(ev, dict):
            continue
        ts = str(ev.get("timestamp") or "")
        if s_bound and ts < s_bound:
            continue
        if u_bound and ts > u_bound:
            continue
        if filt_mt and str(ev.get("memory_type", "")).lower() != filt_mt:
            continue
        if filt_et and str(ev.get("event_type", "")) != filt_et:
            continue
        pn = str(ev.get("project_name", "")).strip().lower()
        if filt_proj and pn != filt_proj and filt_proj not in pn:
            continue
        meta = ev.get("metadata") if isinstance(ev.get("metadata"), dict) else {}
        if filt_sess:
            mid = str(meta.get("session_id") or "")
            if mid != filt_sess:
                continue
        if filt_uk:
            muk = str(meta.get("user_key") or "")
            if muk != filt_uk:
                continue
        out.append(ev)

    out.sort(key=lambda e: str(e.get("timestamp", "")))
    cap = max(1, min(int(limit), 2000))
    return out[-cap:]


def _replay_bundle_from_ordered(ordered: list[dict], *, limit: int) -> dict[str, object]:
    reconstructed: list[str] = []
    for ev in ordered:
        if ev.get("event_type") == "context_injected":
            meta = ev.get("metadata") if isinstance(ev.get("metadata"), dict) else {}
            summaries = meta.get("summaries_ordered")
            if isinstance(summaries, list):
                reconstructed.extend(str(s) for s in summaries if s)
            continue
        if ev.get("event_type") == "memory_retrieved":
            s = str(ev.get("summary") or "").strip()
            if s:
                reconstructed.append(s)

    key_decisions: list[str] = []
    for ev in ordered:
        if ev.get("event_type") in ("concept_created", "memory_created", "concept_merged"):
            s = str(ev.get("summary") or "")
            imp = float(ev.get("importance_score") or 0)
            if (
                imp >= 0.52
                or "decision" in s.lower()
                or "provider" in s.lower()
                or "deepseek" in s.lower()
            ):
                if s and s not in key_decisions:
                    key_decisions.append(s[:220])
        if len(key_decisions) >= 24:
            break

    contradictions: list[dict[str, object]] = []
    for ev in ordered:
        if ev.get("event_type") == "contradiction_detected" or (
            bool(ev.get("contradiction_detected"))
            and ev.get("event_type")
            in ("memory_created", "concept_created", "concept_merged")
        ):
            contradictions.append(
                {
                    "at": ev.get("timestamp"),
                    "memory_ids": (
                        ([ev["memory_id"]] if ev.get("memory_id") else [])
                        + list(ev.get("concept_ids") or [])
                    ),
                    "summary_preview": sanitize_timeline_text(str(ev.get("summary") or ""), 200),
                }
            )

    concept_evolution: dict[str, list[dict[str, object]]] = {}
    for ev in ordered:
        if ev.get("event_type") not in (
            "concept_created",
            "concept_merged",
            "memory_created",
        ):
            continue
        cids = list(ev.get("concept_ids") or [])
        if not cids and ev.get("memory_id"):
            cids = [str(ev.get("memory_id"))]
        for cid in cids:
            concept_evolution.setdefault(cid, []).append(
                {
                    "timestamp": ev.get("timestamp"),
                    "event_type": ev.get("event_type"),
                    "summary": ev.get("summary"),
                }
            )

    return {
        "status": "ok",
        "ordered_events": ordered[-max(1, min(limit, 500)) :],
        "reconstructed_context_summary": "\n".join(reconstructed[-80:])[:8000],
        "key_decisions": key_decisions[:20],
        "contradictions": contradictions[-30:],
        "concept_evolution": concept_evolution,
        "note": "Futur UI timeline : réutiliser ordered_events (MVP JSON).",
    }


def build_replay_payload(
    *,
    project: str = "",
    memory_type: str = "",
    event_type: str = "",
    since: str | None = None,
    until: str | None = None,
    limit: int = 250,
    session_filter: str = "",
    user_filter: str = "",
) -> dict[str, object]:
    filt = filter_timeline_events(
        project=project,
        memory_type=memory_type,
        event_type=event_type,
        since=since,
        until=until,
        limit=min(12000, max(limit, 1) * 48),
        session_id=session_filter,
        user_key=user_filter,
    )
    ordered = sorted(filt, key=lambda e: str(e.get("timestamp", "")))
    return _replay_bundle_from_ordered(ordered, limit=limit)


def build_session_replay(session_id: str, *, limit: int = 200) -> dict[str, object]:
    sid = (session_id or "").strip()
    if not sid:
        return {"status": "error", "detail": "session_id_required"}
    evs = filter_timeline_events(session_id=sid, limit=12000)
    if not evs:
        evs = filter_timeline_events(user_key=sid, limit=12000)
    ordered = sorted(evs, key=lambda e: str(e.get("timestamp", "")))
    payload = _replay_bundle_from_ordered(ordered, limit=limit)
    payload["session_id"] = sid
    return payload


def decision_trace(
    *,
    concept: str,
    project: str = "",
) -> dict[str, object]:
    q = (concept or "").strip().lower()
    if not q:
        return {"status": "error", "detail": "concept_required"}
    proj = (project or "").strip().lower()

    from app.memory import fractal_memory as fm  # noqa: WPS433 — évite cycle import

    try:
        entries = fm.entries_snapshot_for_tests()
    except Exception:
        entries = []

    hits: list[dict] = []
    for e in entries:
        if proj:
            ep = fm._normalize_project_slug(str(e.get("project_name") or ""))  # noqa: SLF001
            if ep != proj and proj not in ep:
                continue
        summ = str(e.get("summary", "")).lower()
        if q in summ or q in str(e.get("user_message", "")).lower():
            hits.append(e)

    hits.sort(key=lambda x: str(x.get("timestamp") or x.get("created_at") or ""))

    concept_rows = [h for h in hits if str(h.get("memory_level")) == "concept_memory"]
    first_seen = None
    if hits:
        first_seen = hits[0].get("created_at") or hits[0].get("timestamp")

    merged_aliases: list[str] = []
    for h in concept_rows:
        md = h.get("metadata") if isinstance(h.get("metadata"), dict) else {}
        al = md.get("aliases")
        if isinstance(al, list):
            merged_aliases.extend(str(x) for x in al if x)
        merged_aliases.append(str(h.get("summary") or ""))

    contradictions = [h for h in concept_rows if h.get("contradiction_detected")]
    latest = concept_rows[-1] if concept_rows else (hits[-1] if hits else None)
    latest_status = str(latest.get("lifecycle_status", "active")) if latest else "unknown"

    imp = float(latest.get("importance_score") or 0.0) if latest else 0.0
    acc = int(latest.get("access_count") or 0) if latest else 0
    confidence_hint = round(min(1.0, 0.35 + imp * 0.45 + min(0.25, acc * 0.02)), 2)

    return {
        "status": "ok",
        "concept_query": concept,
        "project_filter": project or None,
        "first_seen": first_seen,
        "supporting_memories": [
            {
                "id": h.get("id"),
                "memory_type": h.get("memory_type"),
                "memory_level": h.get("memory_level"),
                "summary": sanitize_timeline_text(str(h.get("summary") or ""), 300),
                "timestamp": h.get("timestamp"),
            }
            for h in hits[:40]
        ],
        "merged_aliases": sorted({a for a in merged_aliases if a})[:30],
        "contradictions": len(contradictions),
        "latest_status": latest_status,
        "confidence_hint": confidence_hint,
        "note": "confidence_hint heuristique MVP (importance + access_count).",
    }
