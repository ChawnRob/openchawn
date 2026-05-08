"""
Memory Decision Context Layer V11.6.

Assemble un contexte cognitif multi-couches avant décision/réponse.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.memory import fractal_memory as fm
from app.memory import memory_contradiction_resolution as mcr
from app.memory import memory_relationship_graph as mrg
from app.memory import memory_temporal_evolution as mte
from app.decision import decision_arbitration as dar

_LOCK = Lock()
_LAST_CONTEXT: dict[str, Any] = {"status": "empty"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def select_relevant_memories(entries: list[dict], query: str, *, limit: int = 14) -> list[dict]:
    q = str(query or "").lower()
    ranked: list[tuple[float, dict]] = []
    for e in entries:
        if not fm.is_active_memory(e):
            continue
        txt = " ".join([str(e.get("summary") or ""), str(e.get("user_message") or ""), str(e.get("assistant_response") or "")]).lower()
        imp = float(e.get("importance_score") or 0.0)
        cen = float(e.get("graph_centrality") or 0.0)
        tr = float(e.get("trend_score") or 0.0)
        rec = float(e.get("recurrence_score") or 0.0)
        mmt = float(e.get("momentum_score") or 0.0)
        rel = 0.15 if (q and any(tok in txt for tok in q.split()[:8])) else 0.0
        score = imp * 0.38 + min(0.35, cen * 0.04) + tr * 0.22 + rec * 0.14 + max(0.0, mmt) * 0.08 + rel
        rs = str(e.get("contradiction_resolution_status") or "")
        if rs in ("deprecated", "unresolved", "conflict_active"):
            score -= 0.26
        if rs in ("resolved", "superseded"):
            score += 0.08
        if bool(e.get("human_review_required")):
            score -= 0.18
        ranked.append((score, e))
    ranked.sort(key=lambda x: x[0], reverse=True)
    out = [dict(x[1]) for x in ranked[: max(1, limit)]]
    for i, e in enumerate(out, start=1):
        e["context_weight"] = round(float(ranked[i - 1][0]), 4)
        e["context_priority"] = i
        e["context_selected_at"] = _now_iso()
        e["context_decision_relevance"] = round(
            min(1.0, max(0.0, float(e.get("importance_score") or 0.0) * 0.6 + float(e.get("trend_score") or 0.0) * 0.2 + float(e.get("recurrence_score") or 0.0) * 0.2)),
            4,
        )
    return out


def build_context_clusters(selected_memories: list[dict]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict]] = {}
    for e in selected_memories:
        cid = str(e.get("cluster_id") or "cluster_0")
        groups.setdefault(cid, []).append(e)
    clusters: list[dict[str, Any]] = []
    for cid, rows in groups.items():
        concepts: set[str] = set()
        for r in rows:
            concepts.update([str(x) for x in (r.get("concept_tags") or [])[:16]])
        clusters.append(
            {
                "cluster_id": cid,
                "size": len(rows),
                "avg_importance": round(sum(float(x.get("importance_score") or 0.0) for x in rows) / max(1, len(rows)), 4),
                "avg_trend": round(sum(float(x.get("trend_score") or 0.0) for x in rows) / max(1, len(rows)), 4),
                "concepts": sorted(concepts)[:18],
            }
        )
    clusters.sort(key=lambda x: (float(x["avg_importance"]), int(x["size"])), reverse=True)
    for c in clusters:
        role = "active_core" if int(c["size"]) >= 2 and float(c["avg_importance"]) >= 0.35 else "support"
        c["cluster_role"] = role
    return clusters


def inject_temporal_signals(context: dict[str, Any], entries: list[dict]) -> dict[str, Any]:
    snap = mte.build_temporal_snapshot(entries)
    context["temporal_trends"] = {
        "rising_concepts": snap.get("rising_concepts") or [],
        "declining_concepts": snap.get("declining_concepts") or [],
        "stale_decisions": snap.get("stale_decisions") or [],
    }
    return context


def inject_relationship_signals(context: dict[str, Any], entries: list[dict]) -> dict[str, Any]:
    graph = mrg.build_memory_relationship_graph(entries)
    hubs = graph.get("hubs") or []
    context["dominant_concepts"] = [str((h.get("summary") or "")[:120]) for h in hubs[:8] if str(h.get("summary") or "").strip()]
    return context


def inject_contradiction_signals(context: dict[str, Any], entries: list[dict]) -> dict[str, Any]:
    rep = mcr.build_contradiction_resolution_report(entries)
    unresolved = []
    for e in entries:
        rs = str(e.get("contradiction_resolution_status") or "")
        if rs in ("unresolved", "conflict_active", "needs_human_review"):
            unresolved.append(
                {
                    "memory_id": str(e.get("id") or ""),
                    "status": rs,
                    "resolution_confidence": float(e.get("resolution_confidence") or 0.0),
                    "human_review_required": bool(e.get("human_review_required")),
                }
            )
    context["unresolved_conflicts"] = unresolved[:40]
    context["contradiction_report"] = rep
    return context


def compute_context_confidence(context: dict[str, Any]) -> float:
    base = 0.82
    unresolved = len(context.get("unresolved_conflicts") or [])
    frag = float(context.get("fragmentation_score") or 0.0)
    stale = len(((context.get("temporal_trends") or {}).get("stale_decisions") or []))
    return round(max(0.05, min(1.0, base - unresolved * 0.05 - stale * 0.03 - frag * 0.2)), 4)


def compute_context_stability(context: dict[str, Any]) -> float:
    trends = context.get("temporal_trends") or {}
    rising = len(trends.get("rising_concepts") or [])
    stale = len(trends.get("stale_decisions") or [])
    unresolved = len(context.get("unresolved_conflicts") or [])
    return round(max(0.0, min(1.0, 0.55 + rising * 0.03 - stale * 0.05 - unresolved * 0.04)), 4)


def compute_context_risk(context: dict[str, Any]) -> float:
    unresolved = len(context.get("unresolved_conflicts") or [])
    human = sum(1 for x in (context.get("unresolved_conflicts") or []) if bool(x.get("human_review_required")))
    return round(max(0.0, min(1.0, unresolved * 0.08 + human * 0.12)), 4)


def detect_context_fragmentation(context: dict[str, Any]) -> float:
    clusters = context.get("active_clusters") or []
    if not clusters:
        return 1.0
    sizes = [int(c.get("size") or 0) for c in clusters]
    mx = max(sizes) if sizes else 1
    spread = len([s for s in sizes if s > 0])
    frag = min(1.0, (spread / max(1, len(context.get("selected_memories") or []))) + (0.25 if mx <= 1 else 0.0))
    return round(frag, 4)


def summarize_decision_context(context: dict[str, Any]) -> str:
    return (
        f"selected={len(context.get('selected_memories') or [])};"
        f"clusters={len(context.get('active_clusters') or [])};"
        f"dominant={len(context.get('dominant_concepts') or [])};"
        f"unresolved={len(context.get('unresolved_conflicts') or [])};"
        f"confidence={context.get('context_confidence')};"
        f"stability={context.get('context_stability')};"
        f"risk={context.get('context_risk')};"
        f"fragmentation={context.get('fragmentation_score')}"
    )


def explain_context_selection(context: dict[str, Any]) -> dict[str, Any]:
    items = []
    for e in (context.get("selected_memories") or [])[:20]:
        items.append(
            {
                "memory_id": str(e.get("id") or ""),
                "context_weight": float(e.get("context_weight") or 0.0),
                "context_priority": int(e.get("context_priority") or 0),
                "context_decision_relevance": float(e.get("context_decision_relevance") or 0.0),
                "context_cluster_role": str(e.get("context_cluster_role") or ""),
            }
        )
    return {"status": "ok", "reasoning_summary": context.get("reasoning_summary"), "items": items}


def build_decision_context(
    *,
    query: str = "",
    entries: list[dict] | None = None,
    limit: int = 14,
    persist_annotations: bool = False,
) -> dict[str, Any]:
    rows = [fm._ensure_entry_defaults(dict(e)) for e in ((entries if isinstance(entries, list) else fm.entries_snapshot_for_tests()) or [])]  # noqa: SLF001
    selected = select_relevant_memories(rows, query, limit=limit)
    clusters = build_context_clusters(selected)
    dominant_ids = set()
    for c in clusters:
        if str(c.get("cluster_role")) == "active_core":
            dominant_ids.add(str(c.get("cluster_id") or ""))
    for e in selected:
        e["context_cluster_role"] = "dominant" if str(e.get("cluster_id") or "") in dominant_ids else "support"
    stable_decisions = [e for e in selected if str(e.get("temporal_status") or "") in ("stable", "rising") and str(e.get("contradiction_resolution_status") or "") in ("resolved", "superseded", "")]
    ctx: dict[str, Any] = {
        "status": "ok",
        "selected_memories": selected,
        "dominant_concepts": [],
        "active_clusters": clusters,
        "unresolved_conflicts": [],
        "temporal_trends": {},
        "stable_decisions": [{"memory_id": str(e.get("id") or ""), "summary": str(e.get("summary") or "")[:200]} for e in stable_decisions[:24]],
    }
    ctx = inject_temporal_signals(ctx, rows)
    ctx = inject_relationship_signals(ctx, rows)
    ctx = inject_contradiction_signals(ctx, rows)
    ctx["fragmentation_score"] = detect_context_fragmentation(ctx)
    ctx["context_confidence"] = compute_context_confidence(ctx)
    ctx["context_stability"] = compute_context_stability(ctx)
    ctx["context_risk"] = compute_context_risk(ctx)
    ctx["reasoning_summary"] = summarize_decision_context(ctx)
    options_for_arbitration = []
    for e in selected[:10]:
        options_for_arbitration.append(
            {
                "option_id": f"mem_{str(e.get('id') or '')}",
                "title": str(e.get("summary") or "")[:200],
                "source_memory_ids": [str(e.get("id") or "")],
                "strategy_type": _infer_strategy_from_memory(e),
            }
        )
    try:
        arb = dar.arbitrate_decision(
            project=str((selected[0].get("project_name") if selected else "") or ""),
            decision_type="unknown",
            options=options_for_arbitration,
            entries=rows,
            context=ctx,
        )
    except Exception:
        arb = {"status": "error", "selected_option": None, "options": []}
    ctx["arbitration"] = arb
    if persist_annotations:
        by_id = {str(x.get("id") or ""): x for x in rows if x.get("id")}
        for e in selected:
            mid = str(e.get("id") or "")
            if mid in by_id:
                by_id[mid]["context_weight"] = float(e.get("context_weight") or 0.0)
                by_id[mid]["context_priority"] = int(e.get("context_priority") or 0)
                by_id[mid]["context_selected_at"] = e.get("context_selected_at")
                by_id[mid]["context_cluster_role"] = str(e.get("context_cluster_role") or "")
                by_id[mid]["context_decision_relevance"] = float(e.get("context_decision_relevance") or 0.0)
    with _LOCK:
        global _LAST_CONTEXT
        _LAST_CONTEXT = dict(ctx)
    return ctx


def _infer_strategy_from_memory(mem: dict) -> str:
    txt = " ".join(
        [
            str(mem.get("summary") or ""),
            " ".join([str(t) for t in (mem.get("concept_tags") or [])[:10]]),
        ]
    ).lower()
    if any(k in txt for k in ("deepseek", "openai", "provider", "openrouter", "ollama")):
        return "provider_strategy"
    if any(k in txt for k in ("deployment", "railway", "infra", "prod", "production")):
        return "deployment_strategy"
    if any(k in txt for k in ("memory", "retrieval", "faiss", "compression", "consolidation")):
        return "memory_strategy"
    if any(k in txt for k in ("security", "secret", "token", "apikey", "api key")):
        return "security_strategy"
    if any(k in txt for k in ("cost", "budget", "pricing")):
        return "cost_strategy"
    if any(k in txt for k in ("architecture", "dependency", "module")):
        return "architecture_strategy"
    if any(k in txt for k in ("product", "feature", "user")):
        return "product_strategy"
    return "unknown"

