"""
Cognitive State Engine V11.6 — agrégation heuristique Decision / Reflection / mémoire / graphe / providers.
Sans LLM, embeddings ou agent autonome. Influence légère caps mémoire et formulation confiance.
"""

from __future__ import annotations

import copy
import math
from threading import Lock
from typing import Any

from app.memory import memory_decision_engine as mde
from app.memory import memory_reflection_engine as mem_reflect
from app.memory.memory_timeline import sanitize_timeline_text

_LAST_SNAPSHOT_LOCK = Lock()
_LAST_SNAPSHOT: dict[str, Any] = {
    "status": "empty",
    "state": "stable",
    "pressure_score": 28.0,
    "primary_project": "",
    "primary_concepts": [],
    "contradiction_level": "low",
    "provider_stability": "unknown",
    "retrieval_health": "unknown",
    "memory_health": "unknown",
    "confidence_level": "medium",
}

ALLOWED_STATES = frozenset(
    {
        "stable",
        "focused",
        "exploring",
        "contradicted",
        "overloaded",
        "uncertain",
        "high_confidence",
        "memory_fragmented",
    }
)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _entropy_norm(counts: dict[str, int]) -> float:
    vals = [int(v) for v in counts.values() if int(v) > 0]
    n = len(vals)
    if n <= 1:
        return 0.0
    total = float(sum(vals))
    h = 0.0
    for v in vals:
        p = v / total
        h -= p * math.log(p + 1e-12)
    return float(h / math.log(n))


def normalize_metrics_bundle(
    *,
    lifecycle: dict[str, Any],
    graph: dict[str, Any],
    reflection_agg: dict[str, Any],
    provider_snap: dict[str, dict[str, int]],
    candidate_count: int | None,
    live_bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    lc_status = str(lifecycle.get("status") or "")
    active_m = int(lifecycle.get("active_memories") or 0)
    archived_m = int(lifecycle.get("archived_memories") or 0)
    contra_entries = int(lifecycle.get("contradictions_detected") or 0)
    avg_decay = float(lifecycle.get("average_decay_score") or 0.0)
    mhs = lifecycle.get("memory_health_score")
    mhs_f = float(mhs) if isinstance(mhs, (int, float)) else None

    graph_pairs = int(graph.get("contradiction_pairs_count") or 0)
    graph_flagged = int(graph.get("contradictions_flagged_concepts") or 0)

    bundle_conflicts = 0
    if live_bundle:
        bundle_conflicts = len(live_bundle.get("conflicts_detected") or [])

    contra_bucket = contradiction_level_from_signals(contra_entries, graph_pairs, graph_flagged, bundle_conflicts)

    mem_health_label = memory_health_label_from_lifecycle(lc_status, mhs_f, active_m, archived_m)

    retrieval_overload, retrieval_health = detect_context_overload(candidate_count if candidate_count is not None else -1)

    prov_stab = detect_provider_instability(provider_snap)

    projects_seen = reflection_agg.get("projects_seen") if isinstance(reflection_agg.get("projects_seen"), dict) else {}
    dom_share = dominant_project_share(projects_seen)

    ent = _entropy_norm({str(k): int(v) for k, v in projects_seen.items()}) if projects_seen else 0.0

    return {
        "lifecycle_status": lc_status,
        "active_memories": active_m,
        "archived_memories": archived_m,
        "contradictions_entries": contra_entries,
        "average_decay_score": avg_decay,
        "memory_health_score": mhs_f,
        "graph_pairs": graph_pairs,
        "graph_flagged_concepts": graph_flagged,
        "bundle_conflicts": bundle_conflicts,
        "contradiction_level": contra_bucket,
        "memory_health_label": mem_health_label,
        "retrieval_overload_hint": retrieval_overload,
        "retrieval_health": retrieval_health,
        "provider_stability": prov_stab,
        "dominant_project_share": dom_share,
        "project_entropy_norm": ent,
        "reflection_conflict_rate": float(reflection_agg.get("avg_conflicts_per_snapshot") or 0.0),
        "reflection_decay_avg": float(reflection_agg.get("avg_decay_score_observed") or 0.0),
    }


def contradiction_level_from_signals(
    lifecycle_contra: int,
    graph_pairs: int,
    graph_flagged: int,
    bundle_conflicts: int,
) -> str:
    score = min(
        18,
        lifecycle_contra // 2 + graph_pairs + graph_flagged // 2 + bundle_conflicts * 3,
    )
    if score >= 7:
        return "high"
    if score >= 3:
        return "moderate"
    return "low"


def memory_health_label_from_lifecycle(
    lc_status: str,
    memory_health_score: float | None,
    active_memories: int,
    archived_memories: int,
) -> str:
    if lc_status == "error":
        return "error"
    if memory_health_score is not None:
        if memory_health_score < 38:
            return "fragmented"
        if memory_health_score < 62:
            return "strained"
        return "good"
    ratio_arch = archived_memories / max(1, active_memories + archived_memories)
    if ratio_arch >= 0.35 and active_memories >= 12:
        return "fragmented"
    if ratio_arch >= 0.18:
        return "strained"
    return "good"


def detect_context_overload(candidate_count: int) -> tuple[bool, str]:
    if candidate_count < 0:
        return False, "unknown"
    if candidate_count >= 24:
        return True, "retrieval_very_broad"
    if candidate_count >= 16:
        return True, "retrieval_broad"
    if candidate_count <= 3:
        return False, "retrieval_narrow"
    return False, "retrieval_balanced"


def detect_provider_instability(provider_snap: dict[str, dict[str, int]]) -> str:
    if not provider_snap:
        return "unknown"
    ratios: list[float] = []
    for _p, stats in provider_snap.items():
        if not isinstance(stats, dict):
            continue
        f = int(stats.get("fail") or 0)
        s = int(stats.get("success") or 0)
        tot = f + s
        if tot <= 0:
            continue
        ratios.append(s / tot)
    if not ratios:
        return "unknown"
    worst = min(ratios)
    if worst >= 0.82:
        return "stable"
    if worst >= 0.52:
        return "mixed"
    return "degraded"


def dominant_project_share(projects_seen: dict[str, int]) -> float | None:
    if not projects_seen:
        return None
    total = sum(int(v) for v in projects_seen.values())
    if total <= 0:
        return None
    top = max(int(v) for v in projects_seen.values())
    return round(top / total, 3)


def detect_primary_focus(
    *,
    reflection_agg: dict[str, Any],
    live_bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    projects_seen = reflection_agg.get("projects_seen") if isinstance(reflection_agg.get("projects_seen"), dict) else {}
    primary = ""
    if projects_seen:
        primary = max(projects_seen, key=lambda k: int(projects_seen[k]))
    if live_bundle:
        slug = str(live_bundle.get("project_slug") or "").strip()
        if slug:
            primary = slug

    concepts_out: list[str] = []
    try:
        from app.memory import memory_index as mi

        tc = mi.top_concepts_response(limit=6)
        if str(tc.get("status")) == "ok":
            for it in tc.get("items") or []:
                if not isinstance(it, dict):
                    continue
                s = sanitize_timeline_text(str(it.get("summary") or ""), 140)
                if s:
                    concepts_out.append(s)
    except Exception:
        pass

    return {"primary_project": sanitize_timeline_text(primary, 120), "primary_concepts": concepts_out[:8]}


def compute_cognitive_pressure(
    *,
    metrics: dict[str, Any],
    candidate_count: int | None,
) -> float:
    pressure = 22.0

    cl = str(metrics.get("contradiction_level") or "low")
    if cl == "high":
        pressure += 28.0
    elif cl == "moderate":
        pressure += 14.0

    active_m = int(metrics.get("active_memories") or 0)
    pressure += _clamp((active_m / 95.0) * 22.0, 0.0, 22.0)

    decay = float(metrics.get("average_decay_score") or 0.0)
    pressure += _clamp((decay / 100.0) * 20.0, 0.0, 20.0)

    refl_decay = float(metrics.get("reflection_decay_avg") or 0.0)
    pressure += _clamp((refl_decay / 100.0) * 12.0, 0.0, 12.0)

    refl_cr = float(metrics.get("reflection_conflict_rate") or 0.0)
    pressure += _clamp(refl_cr * 18.0, 0.0, 18.0)

    cc = int(candidate_count) if candidate_count is not None else -1
    if cc >= 0:
        pressure += _clamp((max(0, cc - 8) / 18.0) * 16.0, 0.0, 16.0)

    mem_lab = str(metrics.get("memory_health_label") or "")
    if mem_lab == "fragmented":
        pressure += 12.0
    elif mem_lab == "strained":
        pressure += 6.0

    graph_pairs = int(metrics.get("graph_pairs") or 0)
    pressure += _clamp(graph_pairs * 2.4, 0.0, 14.0)

    dom = metrics.get("dominant_project_share")
    if isinstance(dom, float) and dom >= 0.58:
        pressure -= 10.0

    prov = str(metrics.get("provider_stability") or "")
    if prov == "stable":
        pressure -= 7.0
    elif prov == "degraded":
        pressure += 9.0

    retrieval_overload = bool(metrics.get("retrieval_overload_hint"))
    if retrieval_overload:
        pressure += 10.0

    return round(_clamp(pressure, 0.0, 100.0), 2)


def compute_cognitive_state(*, pressure: float, metrics: dict[str, Any]) -> str:
    contradiction_level = str(metrics.get("contradiction_level") or "low")
    memory_health = str(metrics.get("memory_health_label") or "")
    retrieval_health = str(metrics.get("retrieval_health") or "")
    provider_stability = str(metrics.get("provider_stability") or "")
    dom_share = metrics.get("dominant_project_share")
    pent = float(metrics.get("project_entropy_norm") or 0.0)

    if retrieval_health == "retrieval_very_broad" or pressure >= 79:
        state = "overloaded"
    elif contradiction_level == "high":
        state = "contradicted"
    elif memory_health == "fragmented":
        state = "memory_fragmented"
    elif pressure <= 28 and contradiction_level == "low" and provider_stability in ("stable", "unknown"):
        state = "high_confidence"
    elif isinstance(dom_share, float) and dom_share >= 0.52 and pressure < 54:
        state = "focused"
    elif pent >= 0.82 and pressure < 58:
        state = "exploring"
    elif pressure >= 54:
        state = "uncertain"
    else:
        state = "stable"

    return state if state in ALLOWED_STATES else "stable"


def modifiers_for_pressure(pressure: float) -> dict[str, Any]:
    """Réduit légèrement les quotas session/projet et accentue les pénalités de conflit si pression élevée."""
    from app.memory.memory_decision_engine import MAX_LAYER

    caps = dict(MAX_LAYER)
    conflict_penalty_scale = 1.0
    confidence_scale = 1.0

    if pressure >= 78:
        caps["session"] = max(2, caps["session"] - 3)
        caps["project"] = max(1, caps["project"] - 1)
        conflict_penalty_scale = 1.28
        confidence_scale = 0.88
    elif pressure >= 58:
        caps["session"] = max(3, caps["session"] - 2)
        caps["project"] = max(2, caps["project"] - 1)
        conflict_penalty_scale = 1.15
        confidence_scale = 0.93
    elif pressure >= 42:
        caps["session"] = max(4, caps["session"] - 1)
        conflict_penalty_scale = 1.08
        confidence_scale = 0.97

    return {
        "max_layer_override": caps,
        "conflict_penalty_scale": conflict_penalty_scale,
        "confidence_scale": confidence_scale,
        "pressure_used": pressure,
    }


def memory_modifiers_for_retrieval_pass(
    candidate_count: int,
    *,
    entries: list[dict] | None = None,
) -> dict[str, Any]:
    """Appelé avant arbitrage. Si ``entries`` est fourni (appel sous verrou fractal), évite tout second acquire store."""
    reflection_agg = mem_reflect.analyze_decision_history(mde.get_decision_history())
    from app.routing import get_provider_health_hooks

    provider_snap = get_provider_health_hooks().snapshot()

    if entries is not None:
        from app.memory import fractal_memory as fm
        from app.memory import memory_index as mi

        lifecycle = fm.lifecycle_metrics_from_entries(entries)
        graph = mi.graph_statistics_from_entries(entries)
    else:
        sig = _gather_signal_dicts()
        lifecycle = sig["lifecycle"]
        graph = sig["graph"]

    metrics = normalize_metrics_bundle(
        lifecycle=lifecycle,
        graph=graph,
        reflection_agg=reflection_agg,
        provider_snap=provider_snap,
        candidate_count=candidate_count,
        live_bundle=mde.get_last_decision_bundle(),
    )
    pressure = compute_cognitive_pressure(metrics=metrics, candidate_count=candidate_count)
    mods = modifiers_for_pressure(pressure)
    mods["estimated_pressure_pre_bundle"] = pressure
    return mods


def _gather_signal_dicts() -> dict[str, Any]:
    from app.memory import memory_index as mi
    from app.memory.fractal_memory import memory_lifecycle_health
    from app.routing import get_provider_health_hooks

    return {
        "lifecycle": memory_lifecycle_health(),
        "graph": mi.graph_statistics(),
        "provider_snap": get_provider_health_hooks().snapshot(),
    }


def confidence_level_from_signals(pressure: float, bundle_confidence: float | None) -> str:
    bc = float(bundle_confidence) if isinstance(bundle_confidence, (int, float)) else 0.38
    if pressure <= 34 and bc >= 0.42:
        return "high"
    if pressure >= 64 or bc <= 0.22:
        return "low"
    return "medium"


def build_cognitive_snapshot(
    *,
    live_bundle: dict[str, Any] | None = None,
    candidate_count: int | None = None,
    query_preview: str = "",
    project_slug: str = "",
) -> dict[str, Any]:
    sig = _gather_signal_dicts()
    lifecycle = sig["lifecycle"]
    graph = sig["graph"]
    provider_snap = sig["provider_snap"]

    history = mde.get_decision_history()
    reflection_agg = mem_reflect.analyze_decision_history(history)

    bundle = live_bundle if isinstance(live_bundle, dict) else mde.get_last_decision_bundle()

    metrics = normalize_metrics_bundle(
        lifecycle=lifecycle,
        graph=graph,
        reflection_agg=reflection_agg,
        provider_snap=provider_snap,
        candidate_count=candidate_count,
        live_bundle=bundle,
    )

    pressure = compute_cognitive_pressure(metrics=metrics, candidate_count=candidate_count)

    focus = detect_primary_focus(reflection_agg=reflection_agg, live_bundle=bundle)
    metrics_public = {
        **metrics,
        "primary_project_resolved": focus["primary_project"],
    }

    state = compute_cognitive_state(pressure=pressure, metrics=metrics)
    bundle_conf = bundle.get("confidence_hint") if isinstance(bundle, dict) else None
    conf_level = confidence_level_from_signals(pressure, bundle_conf if isinstance(bundle_conf, (int, float)) else None)

    mods = modifiers_for_pressure(pressure)

    snap = {
        "status": "ok",
        "state": state,
        "pressure_score": pressure,
        "primary_project": focus["primary_project"],
        "primary_concepts": focus["primary_concepts"],
        "contradiction_level": metrics["contradiction_level"],
        "provider_stability": metrics["provider_stability"],
        "retrieval_health": metrics["retrieval_health"],
        "memory_health": metrics["memory_health_label"],
        "confidence_level": conf_level,
        "query_preview": sanitize_timeline_text(query_preview, 240),
        "project_slug_hint": sanitize_timeline_text(project_slug, 120),
        "candidate_count": candidate_count,
        "bundle_confidence_hint": bundle_conf,
        "memory_modifiers": {
            "max_layer_override": mods["max_layer_override"],
            "conflict_penalty_scale": mods["conflict_penalty_scale"],
            "confidence_scale": mods["confidence_scale"],
        },
        "_metrics": metrics_public,
    }

    global _LAST_SNAPSHOT
    with _LAST_SNAPSHOT_LOCK:
        _LAST_SNAPSHOT = copy.deepcopy(snap)
    return snap


def record_post_turn_snapshot(
    *,
    query: str,
    project_slug: str,
    bundle: dict[str, Any],
    candidate_count: int,
) -> dict[str, Any]:
    return build_cognitive_snapshot(
        live_bundle=bundle,
        candidate_count=candidate_count,
        query_preview=(query or "").strip(),
        project_slug=project_slug or "",
    )


def get_last_cognitive_state() -> dict[str, Any]:
    with _LAST_SNAPSHOT_LOCK:
        return copy.deepcopy(_LAST_SNAPSHOT)


def get_confidence_wording_line() -> str:
    """Ligne optionnelle pour le prompt utilisateur (après chargement mémoire)."""
    snap = get_last_cognitive_state()
    if str(snap.get("status") or "") == "empty":
        return ""
    cl = str(snap.get("confidence_level") or "")
    if cl == "low":
        return sanitize_timeline_text(
            "Fiabilité contexte faible : rester bref et signaler explicitement toute incertitude.",
            240,
        )
    if cl == "medium":
        return sanitize_timeline_text(
            "Fiabilité contexte modérée : réponses concises ; distinguer faits et hypothèses.",
            240,
        )
    return ""


def clear_last_cognitive_state_for_tests() -> None:
    with _LAST_SNAPSHOT_LOCK:
        _LAST_SNAPSHOT.clear()
        _LAST_SNAPSHOT.update(
            {
                "status": "empty",
                "state": "stable",
                "pressure_score": 28.0,
                "primary_project": "",
                "primary_concepts": [],
                "contradiction_level": "low",
                "provider_stability": "unknown",
                "retrieval_health": "unknown",
                "memory_health": "unknown",
                "confidence_level": "medium",
            }
        )
