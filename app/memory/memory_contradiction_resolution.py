"""
Memory Contradiction Resolution Layer V11.6.

Classe, arbitre et trace les contradictions sans supprimer l'historique.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.memory import fractal_memory as fm

_LOCK = Lock()
_LAST_REPORT: dict[str, Any] = {"status": "empty"}

_STATUSES = {
    "unresolved",
    "resolved",
    "superseded",
    "deprecated",
    "conflict_active",
    "needs_human_review",
}

_CONTRA_TYPES = {
    "provider_strategy",
    "production_policy",
    "architecture_decision",
    "security_policy",
    "cost_strategy",
    "memory_policy",
    "temporal_obsolescence",
    "factual_conflict",
    "user_preference_conflict",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(raw: Any) -> datetime:
    s = str(raw or "").strip().replace("Z", "+00:00")
    if not s:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _text(e: dict) -> str:
    return " ".join(
        [
            str(e.get("summary") or ""),
            str(e.get("user_message") or ""),
            str(e.get("assistant_response") or ""),
            " ".join([str(t) for t in (e.get("tags") or [])]),
        ]
    ).lower()


def classify_contradiction(a: dict, b: dict) -> str:
    txt = _text(a) + " " + _text(b)
    if any(k in txt for k in ("security", "secret", "token", "api key", "apikey", "bearer", "sk-")):
        return "security_policy"
    if any(k in txt for k in ("provider", "deepseek", "openrouter", "ollama", "routing")):
        return "provider_strategy"
    if any(k in txt for k in ("production", "prod", "default", "principal", "forbid", "interdit")):
        return "production_policy"
    if any(k in txt for k in ("architecture", "dependency", "service", "module")):
        return "architecture_decision"
    if any(k in txt for k in ("cost", "budget", "pricing")):
        return "cost_strategy"
    if any(k in txt for k in ("memory", "consolidation", "compression", "retrieval", "faiss")):
        return "memory_policy"
    return "factual_conflict"


def score_conflicting_memories(a: dict, b: dict) -> dict[str, Any]:
    def _score(e: dict) -> float:
        imp = float(e.get("importance_score") or 0.0)
        ltv = float(e.get("long_term_value") or 0.0)
        cen = float(e.get("graph_centrality") or 0.0)
        risk = float(e.get("contradiction_risk") or 0.0)
        archived = str(e.get("lifecycle_status") or "") == fm.MEMORY_LIFECYCLE_ARCHIVED
        ts = _parse_dt(e.get("updated_at") or e.get("timestamp")).timestamp()
        s = imp * 0.42 + ltv * 0.33 + min(0.25, cen * 0.03) - risk * 0.22 + min(0.2, ts / 10_000_000_000)
        if archived:
            s -= 0.4
        return s

    sa = _score(a)
    sb = _score(b)
    if sa >= sb:
        winner, loser, conf = a, b, min(0.98, 0.55 + (sa - sb))
    else:
        winner, loser, conf = b, a, min(0.98, 0.55 + (sb - sa))
    return {
        "winner_memory_id": str(winner.get("id") or ""),
        "loser_memory_id": str(loser.get("id") or ""),
        "winner_score": round(max(sa, sb), 4),
        "loser_score": round(min(sa, sb), 4),
        "confidence": round(conf, 4),
    }


def mark_memory_superseded(loser: dict, winner: dict, *, reason: str, confidence: float) -> None:
    loser["contradiction_resolution_status"] = "superseded"
    loser["superseded_by"] = str(winner.get("id") or "")
    loser["resolution_reason"] = str(reason or "superseded_by_newer_or_stronger_memory")[:320]
    loser["resolution_confidence"] = float(max(0.0, min(1.0, confidence)))
    loser["resolution_updated_at"] = _now()
    loser["human_review_required"] = False
    loser["indexable"] = False
    loser["deprecated"] = True


def resolve_memory_contradiction(
    entries: list[dict],
    *,
    winner_memory_id: str,
    loser_memory_id: str,
    reason: str = "",
    mode: str = "auto",
) -> dict[str, Any]:
    wi = str(winner_memory_id or "").strip()
    li = str(loser_memory_id or "").strip()
    by = {str(e.get("id") or ""): e for e in entries if e.get("id")}
    if not wi or not li or wi not in by or li not in by or wi == li:
        return {"status": "error", "detail": "invalid_ids"}
    winner = by[wi]
    loser = by[li]
    s = score_conflicting_memories(winner, loser)
    conf = float(s.get("confidence") or 0.5)
    r = str(reason or f"{mode}: arbitration winner={wi} loser={li}")[:320]
    winner["contradiction_resolution_status"] = "resolved"
    winner["supersedes"] = sorted(set(list(winner.get("supersedes") or []) + [li]))[:32]
    winner["resolution_reason"] = r
    winner["resolution_confidence"] = conf
    winner["resolution_updated_at"] = _now()
    winner["human_review_required"] = False
    mark_memory_superseded(loser, winner, reason=r, confidence=conf)
    return {"status": "ok", "winner_memory_id": wi, "loser_memory_id": li, "confidence": conf}


def detect_resolution_candidates(entries: list[dict] | None = None) -> list[dict[str, Any]]:
    rows = [fm._ensure_entry_defaults(dict(e)) for e in ((entries if isinstance(entries, list) else fm.entries_snapshot_for_tests()) or [])]  # noqa: SLF001
    out: list[dict[str, Any]] = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a = rows[i]
            b = rows[j]
            ida = str(a.get("id") or "")
            idb = str(b.get("id") or "")
            if not ida or not idb:
                continue
            if str(a.get("project_name") or a.get("project") or "") != str(b.get("project_name") or b.get("project") or ""):
                continue
            ta, tb = _text(a), _text(b)
            if not ta or not tb:
                continue
            if not any(k in ta and k in tb for k in ("provider", "production", "memory", "security", "architecture", "ollama", "deepseek")):
                continue
            if not (bool(a.get("contradiction_detected")) or bool(b.get("contradiction_detected")) or ("interdit" in ta + tb and "principal" in ta + tb)):
                continue
            ctype = classify_contradiction(a, b)
            sc = score_conflicting_memories(a, b)
            needs_review = ctype == "security_policy" or fm._contains_sensitive_text(ta + " " + tb)  # noqa: SLF001
            status = "needs_human_review" if needs_review else "conflict_active"
            out.append(
                {
                    "type": ctype if ctype in _CONTRA_TYPES else "factual_conflict",
                    "status": status,
                    "memory_ids": [ida, idb],
                    "winner_memory_id": sc.get("winner_memory_id"),
                    "loser_memory_id": sc.get("loser_memory_id"),
                    "confidence": sc.get("confidence"),
                    "reason": "safety_review_required" if needs_review else "auto_candidate",
                }
            )
    return out[:200]


def build_contradiction_resolution_report(entries: list[dict] | None = None) -> dict[str, Any]:
    rows = entries if isinstance(entries, list) else fm.entries_snapshot_for_tests()
    cands = detect_resolution_candidates(rows)
    st: dict[str, int] = {k: 0 for k in _STATUSES}
    for e in rows:
        k = str(e.get("contradiction_resolution_status") or "")
        if k in st:
            st[k] += 1
    return {
        "status": "ok",
        "candidates_count": len(cands),
        "statuses": st,
        "needs_human_review_count": sum(1 for x in cands if str(x.get("status")) == "needs_human_review"),
        "items": cands[:80],
        "updated_at": _now(),
    }


def explain_contradiction_resolution(memory_id: str, entries: list[dict] | None = None) -> dict[str, Any]:
    rows = entries if isinstance(entries, list) else fm.entries_snapshot_for_tests()
    mid = str(memory_id or "").strip()
    by = {str(e.get("id") or ""): e for e in rows if e.get("id")}
    e = by.get(mid)
    if not e:
        return {"status": "error", "detail": "not_found"}
    return {
        "status": "ok",
        "memory_id": mid,
        "contradiction_resolution_status": str(e.get("contradiction_resolution_status") or "unresolved"),
        "superseded_by": str(e.get("superseded_by") or ""),
        "supersedes": list(e.get("supersedes") or [])[:20],
        "resolution_reason": str(e.get("resolution_reason") or ""),
        "resolution_confidence": float(e.get("resolution_confidence") or 0.0),
        "human_review_required": bool(e.get("human_review_required")),
        "resolution_updated_at": e.get("resolution_updated_at"),
    }


def refresh_contradiction_resolutions(*, persist: bool = True) -> dict[str, Any]:
    with _LOCK:
        rows = fm.entries_snapshot_for_tests()
        cands = detect_resolution_candidates(rows)
        auto_resolved = 0
        for c in cands:
            if str(c.get("status")) == "needs_human_review":
                for mid in c.get("memory_ids") or []:
                    for e in rows:
                        if str(e.get("id") or "") == str(mid):
                            e["contradiction_resolution_status"] = "needs_human_review"
                            e["human_review_required"] = True
                            e["resolution_reason"] = "security_or_sensitive_conflict"
                            e["resolution_updated_at"] = _now()
                continue
            conf = float(c.get("confidence") or 0.0)
            if conf < 0.62:
                for mid in c.get("memory_ids") or []:
                    for e in rows:
                        if str(e.get("id") or "") == str(mid):
                            e["contradiction_resolution_status"] = "unresolved"
                            e["resolution_reason"] = "ambiguous_conflict_keep_history"
                            e["resolution_confidence"] = conf
                            e["resolution_updated_at"] = _now()
                continue
            rep = resolve_memory_contradiction(
                rows,
                winner_memory_id=str(c.get("winner_memory_id") or ""),
                loser_memory_id=str(c.get("loser_memory_id") or ""),
                reason=str(c.get("reason") or "auto_resolution"),
                mode="auto",
            )
            if rep.get("status") == "ok":
                auto_resolved += 1
        if persist:
            with fm._STORE_LOCK:  # noqa: SLF001
                fm._save_entries(rows)  # noqa: SLF001
        report = build_contradiction_resolution_report(rows)
        report["auto_resolved"] = auto_resolved
        report["persisted"] = bool(persist)
        global _LAST_REPORT
        _LAST_REPORT = dict(report)
        return report

