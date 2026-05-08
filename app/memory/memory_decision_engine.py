"""
Memory Decision Engine V11.6 — scoring, conflits, arbitrage (heuristiques locales).
Sans LLM, embeddings ou vecteurs. Compatible Railway / futur Postgres.
"""

from __future__ import annotations

import copy
import logging
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.memory.fractal_memory import (
    MEMORY_LIFECYCLE_ARCHIVED,
    _concept_sentiment_signals,
    gather_layered_candidates,
    is_active_memory,
)
from app.memory.memory_index import concept_centrality_influence_maps
from app.memory.memory_timeline import sanitize_timeline_text

logger = logging.getLogger("openchawn.memory.decision_engine")

_LAST_DECISION_LOCK = Lock()
_DECISION_HISTORY_MAX = 96
_DECISION_HISTORY: deque[dict[str, Any]] = deque(maxlen=_DECISION_HISTORY_MAX)
_LAST_DECISION_BUNDLE: dict[str, Any] = {
    "status": "empty",
    "selected_memories": [],
    "rejected_memories": [],
    "conflicts_detected": [],
    "arbitration_summary": "",
    "confidence_hint": None,
    "scoring_breakdown": [],
    "final_context_preview": "",
}

MAX_LAYER = {"system": 2, "user": 2, "project": 3, "session": 5}

_SENSITIVE_TERMS = ("ollama", "deepseek", "provider", "providers", "production", "railway")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: Any) -> datetime | None:
    if not (ts or "").strip():
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _recency_score(entry: dict) -> float:
    dt = _parse_iso(entry.get("timestamp")) or _parse_iso(entry.get("created_at"))
    if not dt:
        return 18.0
    age_d = max(0.0, (_now_utc() - dt).total_seconds() / 86400.0)
    return round(max(0.0, min(52.0, 52.0 - age_d * 2.4)), 2)


def _concept_scores_for_memory(mem: dict, cen_map: dict[str, float], infl_map: dict[str, float]) -> tuple[float, float]:
    mid = str(mem.get("id") or "")
    if str(mem.get("memory_level")) == "concept_memory" and mid:
        return float(cen_map.get(mid, 0.0)), float(infl_map.get(mid, 0.0))
    md = mem.get("metadata") if isinstance(mem.get("metadata"), dict) else {}
    cid = str(md.get("linked_concept_id") or "").strip()
    if cid:
        return float(cen_map.get(cid, 0.0)), float(infl_map.get(cid, 0.0))
    return 0.0, 0.0


def score_memory_candidate(
    mem: dict,
    retrieval_dbg: dict[str, Any],
    cen_map: dict[str, float],
    infl_map: dict[str, float],
    *,
    extra_penalty: float = 0.0,
) -> dict[str, Any]:
    rel_raw = float(retrieval_dbg.get("relevance_score") or 0)
    imp = float(mem.get("importance_score") or retrieval_dbg.get("importance_score") or 0.0)
    decay = float(mem.get("decay_score") or retrieval_dbg.get("decay_score") or 0.0)

    relevance_term = min(88.0, rel_raw * 13.5)
    importance_term = round(min(95.0, imp * 96.0), 2)
    cen_v, inf_v = _concept_scores_for_memory(mem, cen_map, infl_map)
    recency_v = _recency_score(mem)

    flag_pen = 26.0 if bool(mem.get("contradiction_detected")) else 0.0
    contradiction_penalty = round(flag_pen + extra_penalty, 2)

    final_score = round(
        relevance_term + importance_term + cen_v + inf_v + recency_v - decay - contradiction_penalty,
        3,
    )

    return {
        "memory_id": str(mem.get("id") or ""),
        "relevance_score": round(rel_raw, 3),
        "relevance_term": round(relevance_term, 3),
        "importance_score": round(imp, 4),
        "importance_term": importance_term,
        "decay_score": round(decay, 3),
        "centrality_score": round(cen_v, 3),
        "influence_score": round(inf_v, 3),
        "contradiction_penalty": contradiction_penalty,
        "recency_score": recency_v,
        "final_decision_score": final_score,
    }


def detect_candidate_conflicts(scored_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    n = len(scored_rows)
    for i in range(n):
        for j in range(i + 1, n):
            a = scored_rows[i]["memory"]
            b = scored_rows[j]["memory"]
            ia = str(a.get("id") or "")
            ib = str(b.get("id") or "")
            sa = str(a.get("summary") or "").lower()
            sb = str(b.get("summary") or "").lower()

            sub_a, pol_a = _concept_sentiment_signals(sa)
            sub_b, pol_b = _concept_sentiment_signals(sb)
            if sub_a and sub_a == sub_b and pol_a and pol_b and pol_a != pol_b:
                conflicts.append(
                    {
                        "kind": "polarity_conflict_same_subject",
                        "subject": sub_a,
                        "memory_ids": sorted({ia, ib}),
                        "detail": "Polarités opposées détectées sur le même sujet lexical.",
                    }
                )
                continue

            if bool(a.get("contradiction_detected")) and bool(b.get("contradiction_detected")):
                overlap_terms = [t for t in _SENSITIVE_TERMS if t in sa and t in sb]
                if overlap_terms:
                    conflicts.append(
                        {
                            "kind": "dual_contradiction_flag_overlap",
                            "memory_ids": sorted({ia, ib}),
                            "terms": overlap_terms[:6],
                            "detail": "Deux mémoires flag contradiction avec vocabulaire provider/production commun.",
                        }
                    )

            joined = sa + sb
            if ("deepseek" in joined and "ollama" in joined) or ("deepseek" in sa and "ollama" in sb):
                if any(k in joined for k in ("principal", "interdit", "forbid", "ban", "prod")):
                    conflicts.append(
                        {
                            "kind": "provider_cross_tension",
                            "memory_ids": sorted({ia, ib}),
                            "detail": "Signaux croisés DeepSeek/Ollama sur posture prod.",
                        }
                    )
    return conflicts


def _conflict_penalty_for(mem_id: str, conflicts: list[dict[str, Any]]) -> float:
    pen = 0.0
    for c in conflicts:
        mids = c.get("memory_ids") or []
        if mem_id and mem_id in mids:
            kind = str(c.get("kind") or "")
            if kind == "polarity_conflict_same_subject":
                pen += 22.0
            elif kind == "dual_contradiction_flag_overlap":
                pen += 18.0
            else:
                pen += 14.0
    return pen


def _sort_key(row: dict[str, Any]) -> tuple[float, float]:
    mem = row["memory"]
    ts = _parse_iso(mem.get("timestamp")) or _parse_iso(mem.get("created_at"))
    epoch = ts.timestamp() if ts else 0.0
    return (-float(row["breakdown"]["final_decision_score"]), -epoch)


def arbitrate_context_bundle(
    scored_rows: list[dict[str, Any]],
    *,
    conflicts: list[dict[str, Any]],
    max_layer: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    caps = dict(MAX_LAYER)
    if max_layer:
        for k in caps:
            if k in max_layer:
                caps[k] = max(0, int(max_layer[k]))
    ranked = sorted(scored_rows, key=_sort_key)
    selected: list[dict[str, Any]] = []
    counts = {k: 0 for k in caps}

    for row in ranked:
        mem = row["memory"]
        mt = str(mem.get("memory_type") or "session").strip().lower()
        if mt not in caps:
            mt = "session"
        if not is_active_memory(mem):
            continue
        if counts[mt] >= caps[mt]:
            continue
        counts[mt] += 1
        selected.append(row)

    selected_ids = {str(r["memory"].get("id")) for r in selected}
    rejected = [r for r in ranked if str(r["memory"].get("id")) not in selected_ids]
    _ = conflicts  # réservé futures règles déterministes supplémentaires
    return selected, rejected


def explain_context_decision(
    mem: dict,
    *,
    selected: bool,
    arbitration_rank: int,
    breakdown: dict[str, Any],
    penalties: list[str],
    conflicts: list[dict[str, Any]],
    reasons: list[str],
) -> dict[str, Any]:
    mid = str(mem.get("id") or "")
    touch = [c for c in conflicts if mid and mid in (c.get("memory_ids") or [])]
    safe_conflicts: list[dict[str, Any]] = []
    for c in touch:
        safe_conflicts.append(
            {
                "kind": c.get("kind"),
                "detail": sanitize_timeline_text(str(c.get("detail") or ""), 240),
                "subject": c.get("subject"),
            }
        )
    return {
        "selected": selected,
        "final_decision_score": breakdown.get("final_decision_score"),
        "importance_explanation": str(mem.get("importance_explanation") or "")[:280],
        "relationship_summary": (
            "liée à " + ",".join([str(x) for x in (mem.get("related_memory_ids") or [])[:3]])
            if (mem.get("related_memory_ids") or [])
            else ""
        ),
        "reasons": [sanitize_timeline_text(str(x), 200) for x in reasons][:12],
        "penalties": [sanitize_timeline_text(str(x), 200) for x in penalties][:12],
        "conflicts": safe_conflicts[:8],
        "arbitration_rank": arbitration_rank,
    }


def _assemble_context_preview(memories: list[dict]) -> str:
    def lines(label: str, items: list[dict]) -> str:
        if not items:
            return ""
        block = [label]
        for it in items:
            s = str(it.get("summary") or "").strip()
            if s:
                block.append(f"• {s}")
        return "\n".join(block)

    by_mt: dict[str, list[dict]] = {k: [] for k in MAX_LAYER}
    for m in memories:
        mt = str(m.get("memory_type") or "session").strip().lower()
        if mt not in by_mt:
            mt = "session"
        by_mt[mt].append(m)

    parts = [
        lines("── MÉMOIRE SYSTÈME (règles globales OpenChawn) ──", by_mt["system"]),
        lines("── PRÉFÉRENCES UTILISATEUR ──", by_mt["user"]),
        lines("── MÉMOIRE PROJET ──", by_mt["project"]),
        lines("── CONTEXTE SESSION (court terme) ──", by_mt["session"]),
    ]
    return "\n\n".join(p for p in parts if p)


def _confidence_hint_from(selected_rows: list[dict[str, Any]]) -> float:
    if not selected_rows:
        return 0.18
    scores = [float(r["breakdown"]["final_decision_score"]) for r in selected_rows]
    avg = sum(scores) / len(scores)
    return round(max(0.08, min(1.0, avg / 420.0)), 3)


def _snapshot_for_history(bundle: dict[str, Any]) -> dict[str, Any]:
    """Instantané léger pour Memory Reflection (sans texte utilisateur brut)."""
    if str(bundle.get("status") or "") != "ok":
        return {}
    conflicts_out: list[dict[str, Any]] = []
    for c in bundle.get("conflicts_detected") or []:
        if not isinstance(c, dict):
            continue
        conflicts_out.append(
            {
                "kind": sanitize_timeline_text(str(c.get("kind") or ""), 120),
                "memory_ids": sorted({str(x) for x in (c.get("memory_ids") or []) if x}),
                "detail": sanitize_timeline_text(str(c.get("detail") or ""), 280),
                "subject": sanitize_timeline_text(str(c.get("subject") or ""), 120),
                "terms": [sanitize_timeline_text(str(t), 80) for t in (c.get("terms") or [])][:8],
            }
        )
    sel_ids = [str(m.get("id")) for m in bundle.get("selected_memories") or [] if m.get("id")]
    rej_ids = [str(m.get("id")) for m in bundle.get("rejected_memories") or [] if m.get("id")]
    sb = bundle.get("scoring_breakdown") or []
    scoring_lean: list[dict[str, Any]] = []
    for r in sb[:160]:
        if not isinstance(r, dict):
            continue
        scoring_lean.append(
            {
                "memory_id": str(r.get("memory_id") or ""),
                "final_decision_score": float(r.get("final_decision_score") or 0),
                "decay_score": float(r.get("decay_score") or 0),
                "contradiction_penalty": float(r.get("contradiction_penalty") or 0),
            }
        )
    bundle_sig = ",".join(sorted(sel_ids))[:400]
    penalties_archive = 0
    for m in bundle.get("rejected_memories") or []:
        dbg = m.get("_decision_debug") if isinstance(m.get("_decision_debug"), dict) else {}
        pens = dbg.get("penalties") or []
        if any("archived" in str(p).lower() or "inactive" in str(p).lower() for p in pens):
            penalties_archive += 1
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "project_slug": sanitize_timeline_text(str(bundle.get("project_slug") or ""), 120),
        "query_preview": sanitize_timeline_text(str(bundle.get("query_preview") or ""), 240),
        "candidate_count": int(bundle.get("candidate_count") or 0),
        "selected_ids": sel_ids,
        "rejected_ids": rej_ids,
        "conflicts_detected": conflicts_out,
        "confidence_hint": bundle.get("confidence_hint"),
        "scoring_breakdown_lean": scoring_lean,
        "bundle_signature": bundle_sig,
        "archived_rejection_signals": penalties_archive,
    }


def set_last_decision_bundle(payload: dict[str, Any]) -> None:
    global _LAST_DECISION_BUNDLE
    with _LAST_DECISION_LOCK:
        _LAST_DECISION_BUNDLE = copy.deepcopy(payload)
        snap = _snapshot_for_history(payload)
        if snap:
            _DECISION_HISTORY.append(snap)


def get_last_decision_bundle() -> dict[str, Any]:
    with _LAST_DECISION_LOCK:
        return copy.deepcopy(_LAST_DECISION_BUNDLE)


def get_decision_history() -> list[dict[str, Any]]:
    """Copie immuable (liste) des derniers instantanés décision pour Reflection."""
    with _LAST_DECISION_LOCK:
        return list(_DECISION_HISTORY)


def clear_decision_history_for_tests() -> None:
    """Tests uniquement — vide la deque process-local."""
    with _LAST_DECISION_LOCK:
        _DECISION_HISTORY.clear()


def build_memory_decision_bundle(
    *,
    query: str,
    candidates: list[dict],
    entries_snapshot: list[dict],
    project_slug: str,
    capture_last: bool = True,
    max_layer_override: dict[str, int] | None = None,
    conflict_penalty_scale: float = 1.0,
    confidence_scale: float = 1.0,
) -> dict[str, Any]:
    cen_map, infl_map = concept_centrality_influence_maps(entries_snapshot)

    rejected_precheck: list[dict[str, Any]] = []
    work_candidates: list[dict] = []
    for mem in candidates:
        dbg = mem.get("_retrieval_debug") if isinstance(mem.get("_retrieval_debug"), dict) else {}
        if not is_active_memory(mem) or str(mem.get("lifecycle_status")) == MEMORY_LIFECYCLE_ARCHIVED:
            m_copy = dict(mem)
            bd_dummy = {
                "final_decision_score": -500.0,
                "relevance_score": float(dbg.get("relevance_score") or 0),
                "importance_score": float(mem.get("importance_score") or 0),
                "decay_score": float(mem.get("decay_score") or 0),
                "centrality_score": 0.0,
                "influence_score": 0.0,
                "contradiction_penalty": 0.0,
                "recency_score": 0.0,
            }
            m_copy["_decision_debug"] = explain_context_decision(
                mem,
                selected=False,
                arbitration_rank=0,
                breakdown=bd_dummy,
                penalties=["archived_or_inactive_layer_candidate"],
                conflicts=[],
                reasons=["non_eligible_lifecycle"],
            )
            rejected_precheck.append({"memory": m_copy})
            continue
        work_candidates.append(mem)

    pre_rows: list[dict[str, Any]] = []
    for mem in work_candidates:
        dbg = mem.get("_retrieval_debug") if isinstance(mem.get("_retrieval_debug"), dict) else {}
        mid = str(mem.get("id") or "")
        bd = score_memory_candidate(mem, dbg, cen_map, infl_map, extra_penalty=_conflict_penalty_for(mid, []))
        pre_rows.append({"memory": mem, "breakdown": bd})

    conflicts_detected = detect_candidate_conflicts(pre_rows)

    scored_rows: list[dict[str, Any]] = []
    scoring_breakdown: list[dict[str, Any]] = []
    for mem in work_candidates:
        dbg = mem.get("_retrieval_debug") if isinstance(mem.get("_retrieval_debug"), dict) else {}
        mid = str(mem.get("id") or "")
        pen = _conflict_penalty_for(mid, conflicts_detected) * float(conflict_penalty_scale)
        bd = score_memory_candidate(mem, dbg, cen_map, infl_map, extra_penalty=pen)
        reasons = [
            f"layer:{dbg.get('memory_type','')}",
            f"retrieval_rank:{dbg.get('retrieval_rank','')}",
        ]
        if float(bd.get("centrality_score") or 0) > 12:
            reasons.append("concept_graph_boost")
        if float(bd.get("recency_score") or 0) > 35:
            reasons.append("strong_recency")
        penalties_list = []
        if pen > 0:
            penalties_list.append(f"pairwise_conflict_penalty={round(pen, 2)}")
        if bool(mem.get("contradiction_detected")):
            penalties_list.append("contradiction_detected_flag")

        scored_rows.append({"memory": mem, "breakdown": bd, "reasons": reasons, "penalties_list": penalties_list})
        scoring_breakdown.append({"memory_id": mid, **bd})

    selected_rows, rejected_rows = arbitrate_context_bundle(
        scored_rows,
        conflicts=conflicts_detected,
        max_layer=max_layer_override,
    )

    selected_memories: list[dict] = []
    for rank, row in enumerate(selected_rows, start=1):
        mem = dict(row["memory"])
        mem["_decision_debug"] = explain_context_decision(
            mem,
            selected=True,
            arbitration_rank=rank,
            breakdown=row["breakdown"],
            penalties=row["penalties_list"],
            conflicts=conflicts_detected,
            reasons=row["reasons"],
        )
        selected_memories.append(mem)

    rejected_memories: list[dict] = []
    for row in rejected_precheck:
        rejected_memories.append(row["memory"])
    for row in rejected_rows:
        mem = dict(row["memory"])
        mem["_decision_debug"] = explain_context_decision(
            mem,
            selected=False,
            arbitration_rank=0,
            breakdown=row["breakdown"],
            penalties=row["penalties_list"] + ["quota_or_rank_arbitration"],
            conflicts=conflicts_detected,
            reasons=row["reasons"] + ["not_selected_after_arbitration"],
        )
        rejected_memories.append(mem)

    preview = _assemble_context_preview(selected_memories)
    arbitration_summary = sanitize_timeline_text(
        f"selected={len(selected_memories)} rejected={len(rejected_memories)} conflicts={len(conflicts_detected)} "
        f"project={project_slug or '_'} query_len={len((query or '').strip())}",
        360,
    )
    confidence = _confidence_hint_from(selected_rows)
    confidence = round(max(0.05, min(1.0, float(confidence) * float(confidence_scale))), 3)

    bundle = {
        "status": "ok",
        "query_preview": sanitize_timeline_text((query or "").strip(), 240),
        "project_slug": project_slug or "",
        "candidate_count": len(candidates),
        "selected_memories": selected_memories,
        "rejected_memories": rejected_memories,
        "conflicts_detected": conflicts_detected,
        "arbitration_summary": arbitration_summary,
        "confidence_hint": confidence,
        "scoring_breakdown": scoring_breakdown,
        "final_context_preview": preview,
    }
    if capture_last:
        set_last_decision_bundle(bundle)
    return bundle


def simulate_memory_decision(
    *,
    query: str,
    project: str = "",
    user_key: str = "",
    is_guest: bool = False,
) -> dict[str, Any]:
    from app.memory import fractal_memory as fm

    raw = fm.entries_snapshot_for_tests()
    entries_work = [copy.deepcopy(e) for e in raw]
    fm.refresh_lifecycle_decay(entries_work)

    candidates = gather_layered_candidates(
        entries_work,
        query,
        user_key=user_key,
        project_name_hint=project or "",
        is_guest=is_guest,
    )
    slug = fm._normalize_project_slug(project) or fm.detect_project_slug_from_text(query or "")  # noqa: SLF001

    bundle = build_memory_decision_bundle(
        query=query or "",
        candidates=candidates,
        entries_snapshot=entries_work,
        project_slug=slug,
        capture_last=False,
    )
    bundle["simulate"] = True
    return bundle


def lean_decision_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    def lean_mem(m: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": m.get("id"),
            "memory_type": m.get("memory_type"),
            "memory_level": m.get("memory_level"),
            "summary": sanitize_timeline_text(str(m.get("summary") or ""), 320),
            "_decision_debug": m.get("_decision_debug"),
        }

    sel = [lean_mem(dict(x)) for x in (bundle.get("selected_memories") or [])]
    rej = [lean_mem(dict(x)) for x in (bundle.get("rejected_memories") or [])]
    return {
        "status": bundle.get("status"),
        "selected_memories": sel,
        "rejected_memories": rej[:80],
        "conflicts_detected": bundle.get("conflicts_detected") or [],
        "arbitration_summary": bundle.get("arbitration_summary"),
        "confidence_hint": bundle.get("confidence_hint"),
        "scoring_breakdown": bundle.get("scoring_breakdown") or [],
        "final_context_preview": sanitize_timeline_text(str(bundle.get("final_context_preview") or ""), 8000),
    }
