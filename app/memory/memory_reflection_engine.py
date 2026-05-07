"""
Memory Reflection Engine V11.6 — observation des décisions mémoire passées (heuristiques).
Sans LLM, embeddings, vecteurs ou agent autonome. Prépare la future World Impact Layer.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.memory import memory_decision_engine as mde
from app.memory.memory_timeline import sanitize_timeline_text


_DECAY_HIGH_THRESHOLD = 42.0


def analyze_decision_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(history)
    total_conflicts = 0
    project_snaps: Counter[str] = Counter()
    decay_vals: list[float] = []
    contra_pen: list[float] = []
    confidence_hints: list[float] = []
    archive_signals = 0

    for snap in history:
        total_conflicts += len(snap.get("conflicts_detected") or [])
        slug = str(snap.get("project_slug") or "").strip() or "_global"
        project_snaps[slug] += 1
        archive_signals += int(snap.get("archived_rejection_signals") or 0)
        ch = snap.get("confidence_hint")
        if isinstance(ch, (int, float)):
            confidence_hints.append(float(ch))
        for row in snap.get("scoring_breakdown_lean") or []:
            if not isinstance(row, dict):
                continue
            decay_vals.append(float(row.get("decay_score") or 0))
            contra_pen.append(float(row.get("contradiction_penalty") or 0))

    avg_decay = round(sum(decay_vals) / len(decay_vals), 3) if decay_vals else 0.0
    avg_contra = round(sum(contra_pen) / len(contra_pen), 3) if contra_pen else 0.0
    avg_conf_per_snap = round(total_conflicts / n, 3) if n else 0.0
    avg_confidence = round(sum(confidence_hints) / len(confidence_hints), 3) if confidence_hints else None

    return {
        "snapshot_count": n,
        "total_conflicts": total_conflicts,
        "avg_conflicts_per_snapshot": avg_conf_per_snap,
        "projects_seen": dict(project_snaps.most_common(24)),
        "avg_decay_score_observed": avg_decay,
        "avg_contradiction_penalty_observed": avg_contra,
        "avg_confidence_hint": avg_confidence,
        "archived_rejection_signals_total": archive_signals,
    }


def detect_memory_patterns(history: list[dict[str, Any]]) -> dict[str, Any]:
    sel_counts: Counter[str] = Counter()
    rej_counts: Counter[str] = Counter()
    bundle_sigs: Counter[str] = Counter()
    candidate_presence: Counter[str] = Counter()

    for snap in history:
        bundle_sigs[str(snap.get("bundle_signature") or "").strip() or "_empty"] += 1
        sids = [str(x) for x in snap.get("selected_ids") or [] if x]
        rids = [str(x) for x in snap.get("rejected_ids") or [] if x]
        for mid in sids:
            sel_counts[mid] += 1
        for mid in rids:
            rej_counts[mid] += 1
        for mid in set(sids) | set(rids):
            candidate_presence[mid] += 1

    n = len(history) or 1

    def rows(counter: Counter[str], *, selected: bool) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for mid, occ in counter.most_common(40):
            if not mid:
                continue
            denom = candidate_presence[mid] if candidate_presence[mid] else n
            rate = round(occ / denom, 3) if selected else round(occ / denom, 3)
            out.append(
                {
                    "memory_id": mid,
                    "occurrences": occ,
                    "rate_vs_presence": rate,
                }
            )
        return out

    recurring_bundles = [
        {"bundle_signature": sanitize_timeline_text(sig, 420), "occurrences": cnt}
        for sig, cnt in bundle_sigs.most_common(12)
        if sig not in ("_empty",) and cnt >= 2
    ]

    return {
        "selected_memory_patterns": rows(sel_counts, selected=True),
        "rejected_memory_patterns": rows(rej_counts, selected=False),
        "recurring_bundle_signatures": recurring_bundles,
    }


def detect_repeated_conflicts(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sig_counts: Counter[tuple[str, str]] = Counter()
    examples: dict[tuple[str, str], str] = {}

    for snap in history:
        proj = str(snap.get("project_slug") or "").strip() or "_"
        for c in snap.get("conflicts_detected") or []:
            if not isinstance(c, dict):
                continue
            kind = str(c.get("kind") or "")
            mids = tuple(sorted({str(x) for x in (c.get("memory_ids") or []) if x}))
            sig = (kind, mids)
            sig_counts[sig] += 1
            if sig not in examples:
                examples[sig] = proj

    out: list[dict[str, Any]] = []
    for sig, cnt in sig_counts.most_common(40):
        if cnt < 2:
            continue
        kind, mids = sig
        detail_hint = ""
        if mids:
            detail_hint = sanitize_timeline_text(f"pair:{kind}|ids={','.join(mids[:4])}", 200)
        out.append(
            {
                "signature": detail_hint or kind,
                "count": cnt,
                "conflict_kind": kind,
                "example_project": examples.get(sig, ""),
            }
        )
    return out


def detect_unstable_projects(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_proj: dict[str, list[int]] = defaultdict(list)
    for snap in history:
        slug = str(snap.get("project_slug") or "").strip() or "_global"
        by_proj[slug].append(len(snap.get("conflicts_detected") or []))

    out: list[dict[str, Any]] = []
    for slug, counts in by_proj.items():
        if len(counts) < 1:
            continue
        avg_c = sum(counts) / len(counts)
        if avg_c >= 0.85 or sum(counts) >= 3:
            out.append(
                {
                    "project": sanitize_timeline_text(slug, 120),
                    "snapshots": len(counts),
                    "total_conflicts": sum(counts),
                    "avg_conflicts_per_snapshot": round(avg_c, 3),
                }
            )
    out.sort(key=lambda x: (-float(x["avg_conflicts_per_snapshot"]), -int(x["total_conflicts"])))
    return out[:24]


def compute_cognitive_stability(
    history: list[dict[str, Any]],
    *,
    aggregates: dict[str, Any],
    repeated_conflicts: list[dict[str, Any]],
    unstable_projects: list[dict[str, Any]],
    patterns: dict[str, Any],
) -> float:
    """Score 0–100 : plus haut = décisions mémoire plus stables (heuristique)."""
    n = len(history)
    if n == 0:
        return 52.0

    score = 78.0
    ac = float(aggregates.get("avg_conflicts_per_snapshot") or 0)
    score -= min(38.0, ac * 14.0)

    rep_bonus = 0.0
    for row in patterns.get("recurring_bundle_signatures") or []:
        occ = int(row.get("occurrences") or 0)
        if occ >= 3:
            rep_bonus += 4.0
    score += min(12.0, rep_bonus)

    rc = len(repeated_conflicts)
    score -= min(22.0, rc * 7.0)

    up = len(unstable_projects)
    score -= min(18.0, up * 6.0)

    decay = float(aggregates.get("avg_decay_score_observed") or 0)
    score -= min(14.0, max(0.0, decay - 22.0) * 0.35)

    avg_pen = float(aggregates.get("avg_contradiction_penalty_observed") or 0)
    score -= min(16.0, avg_pen * 0.08)

    sel_top = patterns.get("selected_memory_patterns") or []
    if sel_top:
        dom = float(sel_top[0].get("rate_vs_presence") or 0)
        if dom >= 0.7:
            score += 5.0

    return round(max(0.0, min(100.0, score)), 2)


def recommend_memory_optimizations(
    aggregates: dict[str, Any],
    repeated_conflicts: list[dict[str, Any]],
    unstable_projects: list[dict[str, Any]],
    patterns: dict[str, Any],
    history: list[dict[str, Any]],
) -> list[str]:
    recs: list[str] = []

    if repeated_conflicts:
        recs.append(
            "Plusieurs conflits identiques reviennent : fusionner ou clarifier les mémoires "
            "concernées pour réduire les tensions détectées automatiquement."
        )

    for up in unstable_projects[:4]:
        slug = str(up.get("project") or "").strip()
        if slug:
            recs.append(
                sanitize_timeline_text(
                    f"Projet « {slug} » : densité de conflits élevée dans l'historique récent ; "
                    "prioriser une revue des mémoires projet et des flags contradiction.",
                    360,
                )
            )

    decay = float(aggregates.get("avg_decay_score_observed") or 0)
    if decay >= _DECAY_HIGH_THRESHOLD:
        recs.append(
            "Decay moyen élevé sur les candidats observés : renforcer ou rafraîchir les mémoires "
            "clés pour éviter une dégradation du contexte arbitré."
        )

    arch = int(aggregates.get("archived_rejection_signals_total") or 0)
    if arch >= 2:
        recs.append(
            "Nombreuses exclusions liées au cycle de vie (archivé/inactif) : vérifier si des entrées "
            "archivées devraient être réactivées ou dupliquées proprement."
        )

    rej = patterns.get("rejected_memory_patterns") or []
    sel = patterns.get("selected_memory_patterns") or []
    if rej and sel:
        top_rej = str(rej[0].get("memory_id") or "")
        top_sel = str(sel[0].get("memory_id") or "")
        if top_rej == top_sel and top_rej:
            recs.append(
                "Une même mémoire apparaît à la fois comme très sélectionnée et très rejetée "
                "selon les passages : possible oscillation de contexte à stabiliser."
            )

    ollama_hits = 0
    for snap in history:
        for c in snap.get("conflicts_detected") or []:
            if not isinstance(c, dict):
                continue
            blob = " ".join(
                [
                    str(c.get("kind") or ""),
                    str(c.get("detail") or ""),
                    str(c.get("subject") or ""),
                    " ".join(str(t) for t in (c.get("terms") or [])),
                ]
            ).lower()
            if "ollama" in blob:
                ollama_hits += 1
    if ollama_hits >= 2:
        recs.append(
            "Signaux récurrents autour d'Ollama / providers : documenter une politique unique "
            "(prod vs dev) pour réduire les contradictions automatiques."
        )

    if not recs:
        recs.append(
            "Historique décisionnel encore léger ou stable : continuer à observer après plusieurs "
            "échanges réels pour affiner les recommandations."
        )

    return [sanitize_timeline_text(r, 420) for r in recs][:16]


def build_reflection_report() -> dict[str, Any]:
    history = mde.get_decision_history()
    aggregates = analyze_decision_history(history)
    patterns = detect_memory_patterns(history)
    repeated = detect_repeated_conflicts(history)
    unstable = detect_unstable_projects(history)
    stability = compute_cognitive_stability(
        history,
        aggregates=aggregates,
        repeated_conflicts=repeated,
        unstable_projects=unstable,
        patterns=patterns,
    )
    recs = recommend_memory_optimizations(aggregates, repeated, unstable, patterns, history)

    n = aggregates.get("snapshot_count") or 0
    if n == 0:
        summary = (
            "Pas encore d'historique décisionnel capturé dans ce processus. "
            "Les premières traces apparaîtront après des décisions mémoire persistées (ex. /api/chat)."
        )
    else:
        summary = (
            f"Sur {n} instantané(s) : stabilité cognitive estimée à {stability}/100 ; "
            f"{aggregates.get('total_conflicts', 0)} conflit(s) cumulés ; "
            f"{len(unstable)} projet(s) signalé(s) comme instables."
        )

    return {
        "status": "ok",
        "cognitive_stability_score": stability,
        "selected_memory_patterns": patterns.get("selected_memory_patterns") or [],
        "rejected_memory_patterns": patterns.get("rejected_memory_patterns") or [],
        "repeated_conflicts": repeated,
        "unstable_projects": unstable,
        "optimization_recommendations": recs,
        "reflection_summary": sanitize_timeline_text(summary, 720),
    }
