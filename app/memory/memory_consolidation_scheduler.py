"""
Memory Consolidation Scheduler V11.6 — « cognitive sleep cycle » léger hors /chat.

Heuristiques uniquement : pas d’LLM, pas d’embeddings, pas de vector DB, pas d’agent autonome.
Aucune suppression définitive : archivage / compression / fusion concept safe seulement.
"""

from __future__ import annotations

import copy
from threading import Lock
from typing import Any

from app.cognition import cognitive_state_engine as cse
from app.decision import consequence_predictor as cp
from app.memory import fractal_memory as fm
from app.memory import memory_compression as mc
from app.memory import memory_decision_engine as mde
from app.memory import memory_index as mi
from app.memory import memory_reflection_engine as mref
from app.memory.memory_timeline import sanitize_timeline_text

_LAST_REPORT_LOCK = Lock()
_LAST_REPORT: dict[str, Any] = {"status": "empty"}


def _dup_pressure_score(entries: list[dict]) -> float:
    """0–100 : pression doublons (résumés / concepts actifs)."""
    n_active = sum(1 for e in entries if fm.is_active_memory(e))
    cand = mc.find_compression_candidates(entries, include_archived=False)
    clusters = cand.get("clusters") or []
    cluster_score = min(55.0, len(clusters) * 14.0)
    excess = max(0, n_active - 28)
    return float(min(100.0, cluster_score + excess * 0.9))


def _memory_pressure_score(lifecycle: dict[str, Any]) -> float:
    """0–100 : combinaison decay moyen + contradictions."""
    avg_d = float(lifecycle.get("average_decay_score") or 0.0)
    contra = int(lifecycle.get("contradictions_detected") or 0)
    h = lifecycle.get("memory_health_score")
    health = float(h) if isinstance(h, (int, float)) else 50.0
    return float(min(100.0, avg_d * 0.72 + contra * 9.5 + max(0.0, 72.0 - health) * 0.35))


def _contradiction_pressure_score(lifecycle: dict[str, Any]) -> float:
    c = int(lifecycle.get("contradictions_detected") or 0)
    return float(min(100.0, c * 15.5))


def _count_archive_candidates(entries: list[dict]) -> int:
    n = 0
    for e in entries:
        if str(e.get("lifecycle_status")) == fm.MEMORY_LIFECYCLE_ARCHIVED:
            continue
        try:
            acc = int(e.get("access_count") or 0)
        except (TypeError, ValueError):
            acc = 0
        imp = float(e.get("importance_score") or 0.0)
        age = fm._entry_age_days(e)  # noqa: SLF001
        if (
            acc == 0
            and age >= float(fm._MIN_ARCHIVE_AGE_DAYS)  # noqa: SLF001
            and imp <= float(fm._MAX_ARCHIVE_IMPORTANCE) + 1e-9  # noqa: SLF001
            and float(e.get("decay_score", 50)) >= 38.0
        ):
            n += 1
    return n


def _compression_candidate_count(entries: list[dict]) -> int:
    cand = mc.find_compression_candidates(entries, include_archived=False)
    return len(cand.get("clusters") or [])


def build_consolidation_plan(entries: list[dict] | None = None) -> dict[str, Any]:
    """Plan déterministe : signaux pression + comptages (pas d’écriture store)."""
    if entries is None:
        try:
            with fm._STORE_LOCK:  # noqa: SLF001
                snap = [fm._ensure_entry_defaults(dict(e)) for e in fm._load_entries()]  # noqa: SLF001
        except fm.MemoryBackendConfigError as e:
            return {
                "status": "error",
                "config_error": str(e),
                "should_run": False,
                "reason": "backend_indisponible",
                "mode": "none",
            }
        entries = snap
    else:
        entries = [fm._ensure_entry_defaults(dict(e)) for e in entries]  # noqa: SLF001

    lifecycle = fm.lifecycle_metrics_from_entries(entries)
    dup = _dup_pressure_score(entries)
    mem_p = _memory_pressure_score(lifecycle)
    contra_p = _contradiction_pressure_score(lifecycle)
    arch_c = _count_archive_candidates(entries)
    comp_c = _compression_candidate_count(entries)

    snap_cog = cse.get_last_cognitive_state()
    state = str(snap_cog.get("state") or "stable").lower()
    pressure = float(snap_cog.get("pressure_score") or 28.0)
    overloaded = state == "overloaded"
    cog_hot = pressure >= 74.0

    reasons: list[str] = []
    if dup >= 30.0:
        reasons.append("duplicate_pressure")
    if mem_p >= 48.0:
        reasons.append("memory_pressure")
    if overloaded or cog_hot:
        reasons.append("cognitive_overload")
    if comp_c >= 1:
        reasons.append("compression_candidates")
    if arch_c >= 3:
        reasons.append("archive_backlog")

    should_run = bool(
        dup >= 32.0
        or mem_p >= 52.0
        or overloaded
        or cog_hot
        or (comp_c >= 1 and len(entries) >= 12)
        or arch_c >= 6
    )

    mode = "light" if should_run else "idle"
    est = []
    if should_run:
        est.append(
            sanitize_timeline_text(
                f"Consolidation légère estimée : doublons~{dup:.0f}/100, "
                f"santé inverse~{mem_p:.0f}/100, clusters compression~{comp_c}, "
                f"candidats archive~{arch_c}.",
                360,
            )
        )

    safety = [
        "Aucune suppression : archivage et compression conformes aux filtres secrets existants.",
        "Deep consolidation uniquement via POST explicite (aucun cron V11.6).",
        "Pas d’appel LLM ni d’embeddings dans ce module.",
    ]

    return {
        "status": "ok",
        "should_run": should_run,
        "reason": ",".join(reasons) if reasons else "signals_below_threshold",
        "mode": mode,
        "memory_pressure": round(mem_p, 2),
        "duplicate_pressure": round(dup, 2),
        "contradiction_pressure": round(contra_p, 2),
        "archive_candidates": arch_c,
        "compression_candidates": comp_c,
        "estimated_impact": est,
        "safety_notes": safety,
        "cognitive_state": state,
        "cognitive_pressure_score": round(pressure, 2),
        "lifecycle": {
            "active_memories": lifecycle.get("active_memories"),
            "average_decay_score": lifecycle.get("average_decay_score"),
            "contradictions_detected": lifecycle.get("contradictions_detected"),
            "memory_health_score": lifecycle.get("memory_health_score"),
        },
    }


def should_run_consolidation(plan: dict[str, Any] | None = None) -> bool:
    p = plan if isinstance(plan, dict) and plan.get("status") == "ok" else build_consolidation_plan()
    return bool(p.get("should_run"))


def _safe_concept_coalesce(
    entries: list[dict],
    *,
    min_group: int,
    max_groups: int,
) -> dict[str, Any]:
    """Archive les concepts redondants (même projet + même concept_merge_key), jamais les secrets/contradictions."""
    if min_group < 2:
        min_group = 2
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        if str(e.get("memory_level")) != "concept_memory":
            continue
        if not fm.is_active_memory(e):
            continue
        if bool(e.get("contradiction_detected")):
            continue
        if fm._contains_sensitive_text(str(e.get("summary", ""))):  # noqa: SLF001
            continue
        pn = fm._normalize_project_slug(str(e.get("project_name") or e.get("project") or ""))  # noqa: SLF001
        ck = fm.concept_merge_key(str(e.get("summary") or ""))
        if not ck:
            continue
        key = (pn, ck)
        groups.setdefault(key, []).append(e)

    archived = 0
    touched_g = 0
    for (_pn, _ck), lst in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(lst) < min_group:
            continue
        if touched_g >= max_groups:
            break
        touched_g += 1
        lst.sort(key=lambda x: (-float(x.get("importance_score") or 0.0), str(x.get("timestamp") or "")))
        canon = lst[0]
        cid = str(canon.get("id") or "")
        for dup in lst[1:]:
            if str(dup.get("id")) == cid:
                continue
            if str(dup.get("lifecycle_status")) == fm.MEMORY_LIFECYCLE_ARCHIVED:
                continue
            dup["lifecycle_status"] = fm.MEMORY_LIFECYCLE_ARCHIVED
            md = dup.setdefault("metadata", {})
            if isinstance(md, dict):
                md.setdefault("consolidation_coalesced_into", cid)
                md.setdefault("consolidation_coalesced_at", fm._now_iso())  # noqa: SLF001
            archived += 1

    return {"concept_groups_seen": touched_g, "archived_duplicate_concepts": archived}


def _contradiction_scan_summary(entries: list[dict]) -> dict[str, Any]:
    flagged = [str(e.get("id")) for e in entries if bool(e.get("contradiction_detected")) and e.get("id")]
    return {"count": len(flagged), "sample_ids": flagged[:24]}


def _set_last_report(payload: dict[str, Any]) -> None:
    with _LAST_REPORT_LOCK:
        global _LAST_REPORT
        _LAST_REPORT = copy.deepcopy(payload)


def get_last_consolidation_report() -> dict[str, Any]:
    with _LAST_REPORT_LOCK:
        return copy.deepcopy(_LAST_REPORT)


def run_light_consolidation(*, user_key: str = "consolidation_light") -> dict[str, Any]:
    """Cycle léger : compression ciblée, archive rules, decay, coalesce concepts (seuil élevé)."""
    plan = build_consolidation_plan()
    before_ids: set[str] = set()
    report: dict[str, Any] = {
        "status": "ok",
        "mode": "light",
        "at": fm._now_iso(),  # noqa: SLF001
        "plan_snapshot": {k: plan[k] for k in ("should_run", "reason", "mode") if k in plan},
        "actions": {},
        "source_entries_deleted": 0,
    }

    with fm._STORE_LOCK:  # noqa: SLF001
        entries = [fm._ensure_entry_defaults(dict(e)) for e in fm._load_entries()]  # noqa: SLF001
        before_ids = {str(e.get("id")) for e in entries if e.get("id")}
        before_n = len(entries)

        archived = fm.apply_archive_rules(
            entries,
            timeline_user_key=user_key,
            timeline_session_id=user_key,
        )
        fm.refresh_lifecycle_decay(entries)

        coalesce = _safe_concept_coalesce(entries, min_group=3, max_groups=14)

        comp = mc.apply_compression_in_memory(
            entries,
            include_archived=False,
            dry_run=False,
            project=None,
        )

        fm.refresh_lifecycle_decay(entries)
        fm._save_entries(entries)  # noqa: SLF001

        after_ids = {str(e.get("id")) for e in entries if e.get("id")}
        missing = before_ids - after_ids

        report["actions"] = {
            "archive_rules_archived": archived,
            "decay_refreshed": True,
            "concept_coalesce": coalesce,
            "compression": {k: comp.get(k) for k in ("status", "created", "candidates_processed", "persisted") if k in comp},
            "entries_before": before_n,
            "entries_after": len(entries),
        }
        report["source_entries_deleted"] = len(missing)
        report["summary"] = sanitize_timeline_text(
            f"light: archived={archived} coalesce={coalesce.get('archived_duplicate_concepts')} "
            f"compression_batches={comp.get('candidates_processed')}",
            400,
        )

    _set_last_report(report)
    return report


def run_deep_consolidation(*, user_key: str = "consolidation_deep") -> dict[str, Any]:
    """
    Consolidation profonde — **uniquement** via appel API explicite (POST).
    Inclut compression store, coalesce plus agressif, scan contradictions, reflection, impact, index.
    """
    report: dict[str, Any] = {
        "status": "ok",
        "mode": "deep",
        "at": fm._now_iso(),  # noqa: SLF001
        "actions": {},
        "source_entries_deleted": 0,
    }

    archived = 0
    before_n = 0
    contra: dict[str, Any] = {}
    comp: dict[str, Any] = {}

    with fm._STORE_LOCK:  # noqa: SLF001
        entries = [fm._ensure_entry_defaults(dict(e)) for e in fm._load_entries()]  # noqa: SLF001
        before_ids = {str(e.get("id")) for e in entries if e.get("id")}
        before_n = len(entries)

        archived = fm.apply_archive_rules(
            entries,
            timeline_user_key=user_key,
            timeline_session_id=user_key,
        )
        fm.refresh_lifecycle_decay(entries)

        coalesce = _safe_concept_coalesce(entries, min_group=2, max_groups=60)

        comp = mc.apply_compression_in_memory(
            entries,
            include_archived=False,
            dry_run=False,
            project=None,
        )

        fm.refresh_lifecycle_decay(entries)
        contra = _contradiction_scan_summary(entries)
        fm._save_entries(entries)  # noqa: SLF001

        after_ids = {str(e.get("id")) for e in entries if e.get("id")}
        report["source_entries_deleted"] = len(before_ids - after_ids)
        report["actions"] = {
            "archive_rules_archived": archived,
            "concept_coalesce": coalesce,
            "compression": {k: comp.get(k) for k in ("status", "created", "candidates_processed") if k in comp},
            "contradiction_scan": contra,
            "entries_before": before_n,
            "entries_after": len(entries),
        }

    # Lectures sans verrou store (rapports / index reconstruit depuis snapshot interne)
    reflection = mref.build_reflection_report()
    impact = cp.build_impact_report(
        proposed_action=(
            "Consolidation mémoire profonde OpenChawn — maintenance index et alignement concepts "
            "(heuristiques locales, hors LLM)."
        ),
        project="openchawn",
        related_memories=[],
        decision_context=mde.get_last_decision_bundle(),
    )
    index_payload = mi.build_memory_index()

    impact_summary = {
        "likely_benefits": (impact.get("likely_benefits") or [])[:4],
        "likely_risks": (impact.get("likely_risks") or [])[:4],
        "technical_impact": sanitize_timeline_text(str(impact.get("technical_impact") or ""), 520),
        "memory_impact": sanitize_timeline_text(str(impact.get("memory_impact") or ""), 520),
        "confidence_hint": impact.get("confidence_hint"),
        "status": impact.get("status"),
    }

    reflection_summary = {
        "status": reflection.get("status"),
        "cognitive_stability_score": reflection.get("cognitive_stability_score"),
        "reflection_summary": reflection.get("reflection_summary"),
        "optimization_recommendations": (reflection.get("optimization_recommendations") or [])[:6],
    }

    index_summary = {
        "status": index_payload.get("status"),
        "concept_count": index_payload.get("concept_count"),
        "version": index_payload.get("version"),
        "projects_gravity_n": len(index_payload.get("projects_gravity") or []),
    }

    report["actions"]["reflection_report"] = reflection_summary
    report["actions"]["world_impact_summary"] = impact_summary
    report["actions"]["index_rebuild"] = index_summary
    report["summary"] = sanitize_timeline_text(
        f"deep: archived={archived} contradictions_flagged={contra['count']} "
        f"index_concepts={index_summary.get('concept_count')}",
        480,
    )

    _set_last_report(report)
    return report


def run_consolidation_cycle(mode: str = "light") -> dict[str, Any]:
    m = (mode or "light").strip().lower()
    if m == "deep":
        return run_deep_consolidation()
    if m != "light":
        return {"status": "error", "detail": "unsupported_mode", "allowed": ["light", "deep"]}
    pl = build_consolidation_plan()
    if not pl.get("should_run"):
        idle = {
            "status": "ok",
            "mode": "idle",
            "at": fm._now_iso(),  # noqa: SLF001
            "skipped": True,
            "reason": pl.get("reason", "below_threshold"),
        }
        _set_last_report(idle)
        return idle
    return run_light_consolidation()
