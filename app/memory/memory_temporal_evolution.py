"""
Memory Temporal Evolution Layer V11.6.

Suivi heuristique de l'évolution des mémoires/concepts/clusters dans le temps.
Sans LLM/cloud.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.memory import fractal_memory as fm

_TEMPORAL_STATUSES = {"rising", "stable", "declining", "stale", "volatile", "unresolved"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(raw: Any) -> datetime | None:
    s = str(raw or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _days_since(dt: datetime | None) -> float:
    if not dt:
        return 9999.0
    return max(0.0, (_now() - dt).total_seconds() / 86400.0)


def _is_sensitive(e: dict) -> bool:
    txt = " ".join([str(e.get("summary") or ""), str(e.get("user_message") or ""), str(e.get("assistant_response") or "")])
    return fm._contains_sensitive_text(txt)  # noqa: SLF001


def compute_memory_evolution(entry: dict) -> dict[str, Any]:
    if _is_sensitive(entry):
        return {"excluded": True}

    created = _parse_dt(entry.get("created_at") or entry.get("timestamp"))
    last_access = _parse_dt(entry.get("last_accessed_at") or entry.get("updated_at") or entry.get("timestamp"))
    first_seen = created.isoformat() if created else _now_iso()
    last_seen = last_access.isoformat() if last_access else _now_iso()

    age_days = _days_since(created)
    inactive_days = _days_since(last_access)
    access = int(entry.get("access_count") or 0)
    rec = float(entry.get("recurrence_score") or 0.0)
    imp = float(entry.get("importance_score") or 0.0)
    ltv = float(entry.get("long_term_value") or 0.0)
    cen = float(entry.get("graph_centrality") or 0.0)
    risk = float(entry.get("contradiction_risk") or 0.0)
    rs = str(entry.get("contradiction_resolution_status") or "")
    sem_hits = int((entry.get("metadata") or {}).get("semantic_match_hits") or 0) if isinstance(entry.get("metadata"), dict) else 0

    trend = max(-1.0, min(1.0, imp * 0.45 + rec * 0.28 + ltv * 0.25 + min(0.2, cen * 0.03) + min(0.1, sem_hits * 0.02) - risk * 0.35 - min(0.35, inactive_days / 120.0)))
    momentum = max(-1.0, min(1.0, rec * 0.42 + min(0.2, access * 0.02) + min(0.2, sem_hits * 0.03) - min(0.4, inactive_days / 80.0)))
    stability = max(0.0, min(1.0, ltv * 0.48 + imp * 0.26 + min(0.2, cen * 0.02) - risk * 0.28))
    volatility = max(0.0, min(1.0, risk * 0.6 + (0.25 if bool(entry.get("contradiction_detected")) else 0.0) + (0.18 if abs(momentum) > 0.65 else 0.0)))

    status = "stable"
    if rs == "superseded":
        status = "declining" if inactive_days > 20 else "stable"
    if risk >= 0.65:
        status = "unresolved"
    elif inactive_days > 45 and access == 0 and age_days > 45:
        status = "stale"
    elif trend <= -0.22:
        status = "declining"
    elif volatility >= 0.72:
        status = "volatile"
    elif trend >= 0.28 and momentum >= 0.18:
        status = "rising"

    if status not in _TEMPORAL_STATUSES:
        status = "stable"

    explanation = (
        f"trend={trend:.2f}; momentum={momentum:.2f}; stability={stability:.2f}; "
        f"volatility={volatility:.2f}; inactive_days={inactive_days:.1f}; contradiction_risk={risk:.2f}; resolution={rs or 'n/a'}"
    )[:320]

    return {
        "first_seen_at": first_seen,
        "last_seen_at": last_seen,
        "trend_score": round(trend, 4),
        "momentum_score": round(momentum, 4),
        "stability_score": round(stability, 4),
        "volatility_score": round(volatility, 4),
        "temporal_status": status,
        "temporal_explanation": explanation,
        "temporal_updated_at": _now_iso(),
    }


def compute_concept_evolution(entries: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in entries:
        if str(e.get("memory_level") or "") != "concept_memory":
            continue
        te = compute_memory_evolution(e)
        if te.get("excluded"):
            continue
        out.append({"memory_id": str(e.get("id") or ""), "summary": str(e.get("summary") or "")[:220], **te})
    return out


def compute_cluster_evolution(entries: list[dict]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict]] = {}
    for e in entries:
        cid = str(e.get("cluster_id") or "").strip()
        if not cid:
            continue
        groups.setdefault(cid, []).append(e)
    out: list[dict[str, Any]] = []
    for cid, lst in groups.items():
        if not lst:
            continue
        avg_trend = sum(float(e.get("trend_score") or 0.0) for e in lst) / len(lst)
        avg_stab = sum(float(e.get("stability_score") or 0.0) for e in lst) / len(lst)
        avg_vol = sum(float(e.get("volatility_score") or 0.0) for e in lst) / len(lst)
        recent_access = sum(int(e.get("access_count") or 0) for e in lst)
        status = "stable"
        if avg_vol > 0.68:
            status = "volatile"
        elif avg_trend >= 0.22 and recent_access >= max(2, len(lst) // 2):
            status = "rising"
        elif avg_trend <= -0.18:
            status = "declining"
        out.append(
            {
                "cluster_id": cid,
                "size": len(lst),
                "trend_score": round(avg_trend, 4),
                "stability_score": round(avg_stab, 4),
                "volatility_score": round(avg_vol, 4),
                "temporal_status": status,
            }
        )
    out.sort(key=lambda x: (float(x["trend_score"]), int(x["size"])), reverse=True)
    return out


def detect_rising_concepts(entries: list[dict]) -> list[dict[str, Any]]:
    arr = [x for x in compute_concept_evolution(entries) if str(x.get("temporal_status")) in ("rising", "stable") and float(x.get("trend_score") or 0.0) >= 0.2]
    arr.sort(key=lambda x: (float(x.get("trend_score") or 0.0), float(x.get("momentum_score") or 0.0)), reverse=True)
    return arr[:40]


def detect_declining_concepts(entries: list[dict]) -> list[dict[str, Any]]:
    arr = [x for x in compute_concept_evolution(entries) if str(x.get("temporal_status")) in ("declining", "stale") or float(x.get("trend_score") or 0.0) <= -0.2]
    arr.sort(key=lambda x: float(x.get("trend_score") or 0.0))
    return arr[:40]


def detect_stale_decisions(entries: list[dict]) -> list[dict[str, Any]]:
    out = []
    for e in entries:
        if str(e.get("temporal_status") or "") not in ("stale", "declining"):
            continue
        if str(e.get("memory_type") or "") not in ("project", "system", "compressed"):
            continue
        out.append({"memory_id": str(e.get("id") or ""), "summary": str(e.get("summary") or "")[:240], "temporal_status": e.get("temporal_status"), "trend_score": e.get("trend_score")})
    return out[:60]


def detect_growing_contradictions(entries: list[dict]) -> list[dict[str, Any]]:
    out = []
    for e in entries:
        risk = float(e.get("contradiction_risk") or 0.0)
        if bool(e.get("contradiction_detected")) and (risk >= 0.65 or str(e.get("temporal_status") or "") in ("unresolved", "volatile")):
            out.append({"memory_id": str(e.get("id") or ""), "summary": str(e.get("summary") or "")[:240], "contradiction_risk": risk, "temporal_status": e.get("temporal_status")})
    out.sort(key=lambda x: float(x["contradiction_risk"]), reverse=True)
    return out[:60]


def build_temporal_snapshot(entries: list[dict] | None = None) -> dict[str, Any]:
    rows = [fm._ensure_entry_defaults(dict(e)) for e in ((entries if entries is not None else fm.entries_snapshot_for_tests()) or [])]  # noqa: SLF001
    updated = 0
    for i, e in enumerate(rows):
        te = compute_memory_evolution(e)
        if te.get("excluded"):
            continue
        e.update(te)
        rows[i] = e
        updated += 1
    clusters = compute_cluster_evolution(rows)
    return {
        "status": "ok",
        "updated": updated,
        "entries": rows,
        "rising_concepts": detect_rising_concepts(rows),
        "declining_concepts": detect_declining_concepts(rows),
        "stale_decisions": detect_stale_decisions(rows),
        "growing_contradictions": detect_growing_contradictions(rows),
        "cluster_evolution": clusters,
    }


def explain_temporal_evolution(memory_id: str, entries: list[dict] | None = None) -> dict[str, Any]:
    rows = entries if isinstance(entries, list) else fm.entries_snapshot_for_tests()
    mid = str(memory_id or "").strip()
    for e in rows:
        if str(e.get("id") or "") != mid:
            continue
        return {
            "status": "ok",
            "memory_id": mid,
            "temporal_status": e.get("temporal_status"),
            "trend_score": float(e.get("trend_score") or 0.0),
            "momentum_score": float(e.get("momentum_score") or 0.0),
            "stability_score": float(e.get("stability_score") or 0.0),
            "volatility_score": float(e.get("volatility_score") or 0.0),
            "temporal_explanation": str(e.get("temporal_explanation") or ""),
            "first_seen_at": e.get("first_seen_at"),
            "last_seen_at": e.get("last_seen_at"),
            "temporal_updated_at": e.get("temporal_updated_at"),
        }
    return {"status": "error", "detail": "not_found"}


def refresh_temporal_evolution(*, persist: bool = True) -> dict[str, Any]:
    snap = build_temporal_snapshot()
    rows = snap.get("entries") or []
    if persist:
        with fm._STORE_LOCK:  # noqa: SLF001
            fm._save_entries(rows)  # noqa: SLF001
    return {
        "status": "ok",
        "updated": snap.get("updated"),
        "persisted": bool(persist),
        "rising_count": len(snap.get("rising_concepts") or []),
        "declining_count": len(snap.get("declining_concepts") or []),
        "stale_decisions_count": len(snap.get("stale_decisions") or []),
        "growing_contradictions_count": len(snap.get("growing_contradictions") or []),
        "rising_clusters_count": len([x for x in (snap.get("cluster_evolution") or []) if str(x.get("temporal_status")) == "rising"]),
    }

