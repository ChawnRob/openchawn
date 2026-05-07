"""
Index logique des connaissances — mémoire fractale V11.6 (MVP heuristiques).
Pas de vecteurs / embeddings ; JSON et graphe dérivé des entrées store.
Futur Postgres : mêmes champs projetés depuis une vue matérialisée ou table.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.memory.fractal_memory import (
    MemoryBackendConfigError,
    _concept_sentiment_signals,
    _normalize_project_slug,
    entries_snapshot_for_tests,
    is_active_memory,
)
from app.memory.memory_timeline import sanitize_timeline_text

INDEX_VERSION = 1


def _parse_ts(s: Any) -> datetime | None:
    if not (s or "").strip():
        return None
    t = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _first_last_seen(entries: list[dict], linked_ids: list[str], concept_entry: dict) -> tuple[str | None, str | None]:
    times: list[datetime] = []
    for fld0 in ("created_at", "timestamp"):
        dt0 = _parse_ts(concept_entry.get(fld0))
        if dt0:
            times.append(dt0)
    entry_by_id = {str(e.get("id")): e for e in entries if e.get("id")}
    for mid in linked_ids:
        le = entry_by_id.get(mid)
        if not le:
            continue
        for fld in ("created_at", "timestamp", "last_accessed_at"):
            dt = _parse_ts(le.get(fld))
            if dt:
                times.append(dt)
    if not times:
        return None, None
    times.sort()
    return times[0].isoformat(), times[-1].isoformat()


def _collect_linkage(entries: list[dict]) -> tuple[list[dict], dict[str, dict[str, object]]]:
    """Concepts comme nœuds + méta agrégées."""
    concepts_raw = [x for x in entries if str(x.get("memory_level")) == "concept_memory"]
    entry_by_id = {str(x.get("id")): x for x in entries if x.get("id")}

    keyed: dict[str, dict[str, object]] = {}
    for c in concepts_raw:
        cid = str(c.get("id") or "")
        if not cid:
            continue

        md = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        aliases_raw = md.get("aliases") if isinstance(md.get("aliases"), list) else [str(c.get("summary") or "")]
        aliases = sorted(
            {
                sanitize_timeline_text(str(a), max_len=200)
                for a in aliases_raw
                if str(a).strip()
            },
        )

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

        linked_memories = list(dict.fromkeys(linked_memories))

        projects: set[str] = set()
        pn_c = _normalize_project_slug(str(c.get("project_name") or ""))
        if pn_c:
            projects.add(pn_c)
        mt_set: set[str] = set()
        for lm in linked_memories:
            lx = entry_by_id.get(lm)
            if not lx:
                continue
            pnl = _normalize_project_slug(str(lx.get("project_name") or ""))
            if pnl:
                projects.add(pnl)
            mtl = str(lx.get("memory_type") or "").strip().lower()
            if mtl:
                mt_set.add(mtl)

        self_mt = str(c.get("memory_type") or "").strip().lower()
        if self_mt:
            mt_set.add(self_mt)

        contradiction_links: list[dict[str, object]] = []
        if bool(c.get("contradiction_detected")):
            subj_self, pol_self = _concept_sentiment_signals(str(c.get("summary", "")))
            for o in concepts_raw:
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

        keyed[cid] = {
            "entry": c,
            "concept_id": cid,
            "linked_memories": linked_memories,
            "aliases": aliases,
            "linked_projects": sorted(projects),
            "memory_types": sorted(mt_set),
            "contradiction_links": contradiction_links,
            "canonical_summary_safe": sanitize_timeline_text(str(c.get("summary") or ""), 320),
            "linked_memories_count": len(linked_memories),
        }
    return concepts_raw, keyed


def compute_concept_centrality(entries: list[dict]) -> dict[str, float]:
    """Centralité weighted-degree normalisée 0–100 (heuristique)."""
    _, keyed = _collect_linkage(entries)
    if not keyed:
        return {}
    scores: dict[str, float] = {}
    max_deg = 0.0
    for cid, blk in keyed.items():
        lm = int(blk["linked_memories_count"])
        n_contra = len(blk["contradiction_links"])
        md_e = blk["entry"].get("metadata") if isinstance(blk["entry"].get("metadata"), dict) else {}
        merges = float(md_e.get("merge_count") or 1)
        deg_raw = float(lm) + 0.9 * math.sqrt(max(1, n_contra + 1)) + 2.2 * merges**0.45
        scores[cid] = deg_raw
        max_deg = max(max_deg, deg_raw)

    denom = max_deg if max_deg > 1e-9 else 1.0
    return {cid: round(min(100.0, (v / denom) * 100.0), 2) for cid, v in scores.items()}


def compute_concept_influence(entries: list[dict], centrality: dict[str, float] | None = None) -> dict[str, float]:
    """Influence projet + voisinage mémoires (sans sémantique)."""
    _, keyed = _collect_linkage(entries)
    if not keyed:
        return {}
    if centrality is None:
        centrality = compute_concept_centrality(entries)
    entry_by_id = {str(x.get("id")): x for x in entries if x.get("id")}
    imp_vals = [
        float(bl["entry"].get("importance_score") or 0.0) for bl in keyed.values()
    ]
    imp_max = max(max(imp_vals), 1e-6)

    out: dict[str, float] = {}
    for cid, blk in keyed.items():
        spread = max(1, len(blk["linked_projects"]))
        lm = int(blk["linked_memories_count"])
        imp_c = float(blk["entry"].get("importance_score") or 0.0)
        cen = centrality.get(cid, 0.0)
        acc_sum = 0
        for mid in blk["linked_memories"]:
            lx = entry_by_id.get(mid)
            if lx:
                acc_sum += int(lx.get("access_count") or 0)

        burst = math.log1p(float(spread)) * 18.0 + math.log1p(max(1, lm)) * 12.0
        grav = cen * 0.35 + (imp_c / imp_max) * 32.0 + math.log1p(max(1, acc_sum)) * 6.0 + burst * 0.25
        out[cid] = round(min(100.0, grav), 2)
    return out


def percentile_threshold(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    srt = sorted(vals)
    ix = max(0, min(len(srt) - 1, int(round((len(srt) - 1) * q))))
    return float(srt[ix])


def _decay_pressure(row_entry: dict, merge_count: int) -> float:
    d = float(row_entry.get("decay_score") or 0.0)
    relief = float(merge_count) ** 0.35
    return round(min(100.0, max(0.0, d / (1.05 + relief))), 4)


def _derive_status(
    *,
    archived: bool,
    contradicted: bool,
    centrif: float,
    influ: float,
    decay_pressure_v: float,
    cohort_pressures: list[float],
    cohort_centrals: list[float],
    cohort_influ: list[float],
) -> str:
    if archived:
        return "archived"
    if contradicted:
        return "contradicted"
    if not cohort_pressures or not cohort_centrals:
        return "stable"

    p_hi = percentile_threshold(cohort_pressures, 0.65)
    c_hi = percentile_threshold(cohort_centrals, 0.72)
    c_lo = percentile_threshold(cohort_centrals, 0.38)
    inf_med = percentile_threshold(cohort_influ, 0.52)

    if centrif >= c_hi and influ >= inf_med:
        return "hot"
    if decay_pressure_v >= p_hi and centrif <= c_lo:
        return "fading"
    return "stable"


def detect_hot_concepts(index_rows: list[dict]) -> list[str]:
    return [str(r.get("concept_id")) for r in index_rows if r.get("status") == "hot" and str(r.get("concept_id"))]


def detect_dying_concepts(index_rows: list[dict]) -> list[str]:
    return [
        str(r.get("concept_id"))
        for r in index_rows
        if r.get("status") in ("fading", "contradicted", "archived") and float(r.get("decay_pressure") or 0) >= 52.0
    ]


def _finalize_concept_rows(drafted: list[dict[str, object]]) -> None:
    pressures = [float(d["_pressure"]) for d in drafted]
    centrals = [float(d["_centr"]) for d in drafted]
    influs = [float(d["_influ"]) for d in drafted]

    for d in drafted:
        d["status"] = _derive_status(
            archived=bool(d["_archived"]),
            contradicted=bool(d["_contrad"]),
            centrif=float(d["centrality_score"] or 0),
            influ=float(d["influence_score"] or 0),
            decay_pressure_v=float(d["decay_pressure"] or 0),
            cohort_pressures=pressures,
            cohort_centrals=centrals,
            cohort_influ=influs,
        )

    drop = {"_pressure", "_centr", "_influ", "_contrad", "_archived"}
    for d in drafted:
        for k in drop:
            d.pop(k, None)


def _draft_concepts_from_entries(entries: list[dict]) -> list[dict[str, object]]:
    _, keyed = _collect_linkage(entries)
    centrality = compute_concept_centrality(entries)
    influence = compute_concept_influence(entries, centrality)

    drafted: list[dict[str, object]] = []
    for cid, blk in keyed.items():
        ce = blk["entry"]
        md = ce.get("metadata") if isinstance(ce.get("metadata"), dict) else {}
        mc = max(1, int(md.get("merge_count") or 1))

        contradiction_links = blk["contradiction_links"]
        contrad_flag = bool(ce.get("contradiction_detected"))
        contradiction_count = int(bool(contrad_flag)) + len(contradiction_links)

        archived_flag = not is_active_memory(ce)
        first_seen, last_seen = _first_last_seen(entries, blk["linked_memories"], ce)
        dp = _decay_pressure(ce, mc)

        drafted.append(
            {
                "_archived": archived_flag,
                "_contrad": contrad_flag or bool(contradiction_links),
                "_centr": float(centrality.get(cid, 0.0)),
                "_influ": float(influence.get(cid, 0.0)),
                "_pressure": float(dp),
                "concept_id": cid,
                "canonical_summary": blk["canonical_summary_safe"],
                "aliases": blk["aliases"][:48],
                "linked_memories_count": blk["linked_memories_count"],
                "linked_projects": blk["linked_projects"],
                "memory_types": blk["memory_types"],
                "merge_count": mc,
                "contradiction_count": contradiction_count,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "centrality_score": centrality.get(cid, 0.0),
                "influence_score": influence.get(cid, 0.0),
                "decay_pressure": dp,
                "status": "_pending",
            }
        )

    _finalize_concept_rows(drafted)
    return drafted


def compute_project_gravity(
    entries: list[dict],
    indexed_concepts: list[dict] | None = None,
) -> list[dict[str, object]]:
    """Gravité par slug projet (aucune récursion vers build_memory_index si concepts fourni)."""
    grouped: defaultdict[str, list[dict]] = defaultdict(list)
    for e in entries:
        pn = _normalize_project_slug(str(e.get("project_name") or e.get("project") or "general"))
        grouped[pn or "_none"].append(e)

    indexed = indexed_concepts if indexed_concepts is not None else _draft_concepts_from_entries(entries)

    rows: list[dict[str, object]] = []
    for proj_key, items in grouped.items():
        active = [e for e in items if is_active_memory(e)]
        total_mem = len(items)
        act_n = len(active)

        avg_imp_vals = [float(e.get("importance_score") or 0.0) for e in active]
        avg_imp = round(sum(avg_imp_vals) / len(avg_imp_vals), 4) if avg_imp_vals else 0.0
        avg_dec_vals = [float(e.get("decay_score") or 0.0) for e in active]
        avg_dec = round(sum(avg_dec_vals) / len(avg_dec_vals), 4) if avg_dec_vals else 0.0

        contradiction_count_proj = sum(1 for e in items if bool(e.get("contradiction_detected")))

        cand: list[tuple[float, dict[str, Any]]] = []
        for ic in indexed:
            if not isinstance(ic, dict):
                continue
            lps = ic.get("linked_projects") or []
            if not isinstance(lps, list):
                continue
            if proj_key in lps:
                score = float(ic.get("centrality_score") or 0.0) + float(ic.get("influence_score") or 0.0)
                cand.append((score, ic))
        cand.sort(key=lambda x: x[0], reverse=True)

        top_slices = cand[: min(12, len(cand))]
        top_concepts_payload = [
            {
                "concept_id": tp[1].get("concept_id"),
                "snippet": sanitize_timeline_text(str(tp[1].get("canonical_summary") or ""), 120),
                "centrality_score": tp[1].get("centrality_score"),
                "status": tp[1].get("status"),
            }
            for tp in top_slices
        ]

        top_strength = sum(
            float(ic.get("centrality_score") or 0.0) for _, ic in top_slices[: min(8, len(top_slices))]
        )

        grav = round(
            min(
                100.0,
                act_n * 1.85
                + avg_imp * 44.0
                - avg_dec * 0.22
                + top_strength * 0.45
                - contradiction_count_proj * 1.85,
            ),
            2,
        )
        if active and grav < 0.05:
            grav = round(0.05, 2)
        grav = round(max(grav, 0.0), 2)

        rows.append(
            {
                "project_name": proj_key if proj_key != "_none" else "general",
                "total_memories": total_mem,
                "active_memories": act_n,
                "top_concepts": top_concepts_payload,
                "contradiction_count": int(contradiction_count_proj),
                "average_importance": avg_imp,
                "average_decay": avg_dec,
                "gravity_score": grav,
            }
        )

    rows.sort(key=lambda r: (-float(r["gravity_score"]), str(r["project_name"])))
    return rows


def build_memory_index() -> dict[str, object]:
    try:
        entries = entries_snapshot_for_tests()
    except MemoryBackendConfigError as e:
        return {"status": "error", "config_error": str(e), "concepts": [], "projects_gravity": [], "version": INDEX_VERSION}

    if not isinstance(entries, list):
        entries = []

    drafted = _draft_concepts_from_entries(entries)
    drafted.sort(key=lambda x: (-float(x.get("centrality_score") or 0), str(x.get("concept_id"))))

    projects_gravity = compute_project_gravity(entries, drafted)
    hot = detect_hot_concepts(drafted)
    dying = detect_dying_concepts(drafted)

    return {
        "status": "ok",
        "version": INDEX_VERSION,
        "concept_count": len(drafted),
        "hot_concepts": hot,
        "dying_concepts_watchlist": dying,
        "concepts": drafted,
        "projects_gravity": projects_gravity,
        "note": "Futur semantic layer : pondérations PMI / embeddings hors scope MVP.",
    }


def top_concepts_response(limit: int = 10) -> dict[str, object]:
    caps = max(1, min(80, int(limit)))
    full = build_memory_index()
    if full.get("status") != "ok":
        return full
    concepts = list(full.get("concepts") or [])
    ranked = sorted(
        concepts,
        key=lambda x: (-float(x.get("centrality_score") or 0), -float(x.get("influence_score") or 0)),
    )
    sliced = ranked[:caps]
    return {
        "status": "ok",
        "limit": caps,
        "count": len(sliced),
        "items": sliced,
    }


def projects_gravity_board() -> dict[str, object]:
    try:
        entries = entries_snapshot_for_tests()
    except MemoryBackendConfigError as e:
        return {"status": "error", "config_error": str(e), "projects": []}
    if not isinstance(entries, list):
        entries = []
    rows = compute_project_gravity(entries)
    return {"status": "ok", "count": len(rows), "projects": rows}


def graph_statistics() -> dict[str, object]:
    try:
        entries = entries_snapshot_for_tests()
    except MemoryBackendConfigError as e:
        return {"status": "error", "config_error": str(e), "concept_node_count": 0}

    _, keyed = _collect_linkage(entries)
    oriented_edges = sum(int(b["linked_memories_count"]) for b in keyed.values())
    concepts_n = len(keyed)

    contradictory_concepts = sum(
        1 for b in keyed.values() if b["contradiction_links"] or bool(b["entry"].get("contradiction_detected"))
    )

    pair_set: set[tuple[str, str]] = set()
    for cid, b in keyed.items():
        for l in b["contradiction_links"]:
            oid = str(l.get("other_concept_id") or "")
            if oid:
                pair_set.add(tuple(sorted((cid, oid))))

    return {
        "status": "ok",
        "concept_node_count": concepts_n,
        "oriented_concept_edges": oriented_edges,
        "avg_linked_memories": round(oriented_edges / concepts_n, 4) if concepts_n else None,
        "contradictions_flagged_concepts": contradictory_concepts,
        "contradiction_pairs_count": len(pair_set),
        "note": "MVP graphe dirigé depuis concepts vers mémoires liées uniquement.",
    }
