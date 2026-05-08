"""
Memory Relationship Graph Layer V11.6.

Graphe heuristique local (sans LLM/cloud) pour relier les mémoires et
fournir des signaux de centralité/cluster utilisables par retrieval,
consolidation, contradiction analysis et decision engine.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.memory import fractal_memory as fm

_LOCK = Lock()

_REL_TYPES = (
    "semantic_similarity",
    "shared_project",
    "provider_strategy",
    "contradiction",
    "chronology",
    "architecture_dependency",
    "repeated_decision",
    "causal_relation",
    "consolidation_relation",
)

_PROVIDER_TOKENS = ("deepseek", "openrouter", "provider", "routing")
_INFRA_TOKENS = ("railway", "deployment", "observability", "monitoring")
_COG_TOKENS = ("faiss", "semantic", "embedding", "retrieval", "cognition")
_TECH_TOKENS = (
    "architecture",
    "dependency",
    "decision",
    "security",
    "memory",
    "postgres",
    "redis",
    "index",
)
_NOISE_TOKENS = ("ok", "merci", "salut", "hello", "hi", "thanks")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(e: dict) -> str:
    return " ".join(
        [
            str(e.get("summary") or ""),
            str(e.get("user_message") or ""),
            str(e.get("assistant_response") or ""),
            " ".join([str(t) for t in (e.get("tags") or [])]),
            str(e.get("project_name") or e.get("project") or ""),
            str(e.get("memory_type") or ""),
        ]
    ).strip()


def _tokens(s: str) -> set[str]:
    return {x for x in re.findall(r"[a-zA-Z0-9_àâäéèêëïîôùûçñáíóúü]{3,}", (s or "").lower())}


def extract_memory_concepts(memory: dict) -> list[str]:
    txt = _text(memory).lower()
    toks = _tokens(txt)
    out: set[str] = set()
    md = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    if int(md.get("retrieval_hits") or 0) >= 2:
        out.add("retrieval_reused")
    if int(md.get("semantic_match_hits") or 0) >= 1:
        out.add("semantic_match")
    linked = str(md.get("linked_concept_id") or "").strip()
    if linked:
        out.add(linked.lower())
    for t in memory.get("tags") or []:
        t0 = str(t).strip().lower()
        if t0:
            out.add(t0)
    for keyset in (_PROVIDER_TOKENS, _INFRA_TOKENS, _COG_TOKENS, _TECH_TOKENS):
        for k in keyset:
            if k in txt or k in toks:
                out.add(k)
    pn = str(memory.get("project_name") or memory.get("project") or "").strip().lower()
    if pn:
        out.add(pn)
    if bool(memory.get("contradiction_detected")):
        out.add("contradiction")
    return sorted(out)[:40]


def compute_relationship_strength(a: dict, b: dict) -> dict[str, Any]:
    ta = _text(a).lower()
    tb = _text(b).lower()
    ka = _tokens(ta)
    kb = _tokens(tb)
    if not ka or not kb:
        return {"score": 0.0, "relations": []}

    relations: list[tuple[str, float]] = []
    inter = ka.intersection(kb)
    uni = ka.union(kb)
    jacc = len(inter) / max(1, len(uni))
    if jacc >= 0.14:
        relations.append(("semantic_similarity", min(0.45, jacc * 1.8)))

    pa = str(a.get("project_name") or a.get("project") or "").strip().lower()
    pb = str(b.get("project_name") or b.get("project") or "").strip().lower()
    if pa and pa == pb:
        relations.append(("shared_project", 0.18))

    if any(k in inter for k in _PROVIDER_TOKENS):
        relations.append(("provider_strategy", 0.2))
    if any(k in inter for k in _TECH_TOKENS):
        relations.append(("architecture_dependency", 0.16))
    if any(k in inter for k in _INFRA_TOKENS):
        relations.append(("causal_relation", 0.14))
    if any(k in inter for k in _COG_TOKENS):
        relations.append(("consolidation_relation", 0.16))

    # chronology: proche en temps => relation légère
    tsa = str(a.get("timestamp") or "").replace("Z", "+00:00")
    tsb = str(b.get("timestamp") or "").replace("Z", "+00:00")
    try:
        da = datetime.fromisoformat(tsa)
        db = datetime.fromisoformat(tsb)
        if da.tzinfo is None:
            da = da.replace(tzinfo=timezone.utc)
        if db.tzinfo is None:
            db = db.replace(tzinfo=timezone.utc)
        dd = abs((da.astimezone(timezone.utc) - db.astimezone(timezone.utc)).total_seconds()) / 86400.0
        if dd <= 3.0:
            relations.append(("chronology", 0.08))
    except Exception:
        pass

    # repeated decision
    md_a = a.get("metadata") if isinstance(a.get("metadata"), dict) else {}
    md_b = b.get("metadata") if isinstance(b.get("metadata"), dict) else {}
    if str(md_a.get("linked_concept_id") or "").strip() and str(md_a.get("linked_concept_id") or "") == str(
        md_b.get("linked_concept_id") or ""
    ):
        relations.append(("repeated_decision", 0.2))
    if int(md_a.get("retrieval_hits") or 0) >= 2 and int(md_b.get("retrieval_hits") or 0) >= 2:
        relations.append(("semantic_similarity", 0.1))

    # contradiction => relation négative
    has_contradiction_rel = False
    if bool(a.get("contradiction_detected")) or bool(b.get("contradiction_detected")):
        if any(k in inter for k in ("ollama", "deepseek", "provider", "production", "routing")):
            relations.append(("contradiction", -0.45))
            has_contradiction_rel = True

    # compressed inherits major relations
    if str(a.get("memory_type")) == "compressed" or str(b.get("memory_type")) == "compressed":
        relations.append(("consolidation_relation", 0.12))

    # noise memories should barely relate
    if any(t in ta for t in _NOISE_TOKENS) and len(ta) < 44:
        relations = [(r, v * 0.22) if r != "contradiction" else (r, v) for r, v in relations]
    if any(t in tb for t in _NOISE_TOKENS) and len(tb) < 44:
        relations = [(r, v * 0.22) if r != "contradiction" else (r, v) for r, v in relations]

    total = sum(v for _, v in relations)
    if has_contradiction_rel:
        total = min(total, -0.2)
    total = max(-1.0, min(1.0, total))
    rel_out = [{"type": r, "weight": round(v, 4)} for r, v in relations if r in _REL_TYPES]
    return {"score": round(total, 4), "relations": rel_out}


def link_related_memories(entries: list[dict]) -> dict[str, Any]:
    n = len(entries)
    by_id = {str(e.get("id") or ""): e for e in entries if e.get("id")}
    rel_map: dict[str, dict[str, float]] = {mid: {} for mid in by_id}
    rel_types: dict[str, dict[str, list[str]]] = {mid: {} for mid in by_id}

    mids = list(by_id.keys())
    for i in range(len(mids)):
        for j in range(i + 1, len(mids)):
            a = by_id[mids[i]]
            b = by_id[mids[j]]
            rep = compute_relationship_strength(a, b)
            score = float(rep.get("score") or 0.0)
            if abs(score) < 0.08:
                continue
            rel_map[mids[i]][mids[j]] = score
            rel_map[mids[j]][mids[i]] = score
            rel_types[mids[i]][mids[j]] = [str(x.get("type")) for x in (rep.get("relations") or [])]
            rel_types[mids[j]][mids[i]] = [str(x.get("type")) for x in (rep.get("relations") or [])]

    return {"status": "ok", "pairs_evaluated": (n * (n - 1)) // 2, "relationships": rel_map, "relation_types": rel_types}


def detect_memory_clusters(entries: list[dict], relationships: dict[str, dict[str, float]]) -> dict[str, str]:
    by_id = {str(e.get("id") or ""): e for e in entries if e.get("id")}
    cluster: dict[str, str] = {}
    visited: set[str] = set()
    cid = 0
    for mid in by_id:
        if mid in visited:
            continue
        cid += 1
        label = f"cluster_{cid}"
        q: deque[str] = deque([mid])
        visited.add(mid)
        while q:
            cur = q.popleft()
            cluster[cur] = label
            for nb, sc in (relationships.get(cur) or {}).items():
                if nb in visited:
                    continue
                if float(sc) < 0.12:
                    continue
                visited.add(nb)
                q.append(nb)
    return cluster


def detect_concept_hubs(entries: list[dict], relationships: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    by_id = {str(e.get("id") or ""): e for e in entries if e.get("id")}
    hubs: list[dict[str, Any]] = []
    for mid, e in by_id.items():
        nb = relationships.get(mid) or {}
        deg = len(nb)
        cent = sum(abs(float(v)) for v in nb.values())
        md = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        if str(e.get("memory_level") or "") == "concept_memory":
            cent += 0.35
        if str(md.get("linked_concept_id") or "").strip():
            cent += 0.2
        hubs.append({"memory_id": mid, "degree": deg, "centrality": round(cent, 4), "summary": str(e.get("summary") or "")[:220]})
    hubs.sort(key=lambda x: (float(x["centrality"]), int(x["degree"])), reverse=True)
    return hubs[:80]


def build_memory_relationship_graph(entries: list[dict] | None = None) -> dict[str, Any]:
    owned = entries is None
    if entries is None:
        entries = fm.entries_snapshot_for_tests()
    rows = [fm._ensure_entry_defaults(dict(e)) for e in (entries or [])]  # noqa: SLF001
    links = link_related_memories(rows)
    rel = links.get("relationships") or {}
    rtypes = links.get("relation_types") or {}
    clusters = detect_memory_clusters(rows, rel)
    hubs = detect_concept_hubs(rows, rel)
    cent_map = {str(h["memory_id"]): float(h["centrality"]) for h in hubs}
    deg_map = {str(h["memory_id"]): int(h["degree"]) for h in hubs}

    by_id = {str(e.get("id") or ""): e for e in rows if e.get("id")}
    for mid, e in by_id.items():
        nb = rel.get(mid) or {}
        e["related_memory_ids"] = sorted(nb.keys(), key=lambda x: abs(float(nb[x])), reverse=True)[:32]
        e["relationship_strengths"] = {k: round(float(v), 4) for k, v in sorted(nb.items(), key=lambda kv: -abs(float(kv[1])))[:32]}
        e["relationship_types"] = {k: (rtypes.get(mid) or {}).get(k, []) for k in e["related_memory_ids"]}
        e["concept_tags"] = extract_memory_concepts(e)
        e["cluster_id"] = clusters.get(mid, "cluster_0")
        e["graph_degree"] = int(deg_map.get(mid, 0))
        e["graph_centrality"] = round(float(cent_map.get(mid, 0.0)), 4)
        e["temporal_status"] = str(e.get("temporal_status") or "")
        e["relationship_updated_at"] = _now_iso()

    return {
        "status": "ok",
        "owned_store": owned,
        "nodes": len(by_id),
        "pairs_evaluated": int(links.get("pairs_evaluated") or 0),
        "clusters_count": len(set(clusters.values())) if clusters else 0,
        "hubs": hubs[:20],
        "entries": rows,
    }


def find_related_memories(memory_id: str, *, limit: int = 12, entries: list[dict] | None = None) -> list[dict[str, Any]]:
    mid = str(memory_id or "").strip()
    if not mid:
        return []
    rows = entries if isinstance(entries, list) else fm.entries_snapshot_for_tests()
    by_id = {str(e.get("id") or ""): e for e in rows if e.get("id")}
    cur = by_id.get(mid)
    if not cur:
        return []
    rel = cur.get("relationship_strengths") if isinstance(cur.get("relationship_strengths"), dict) else {}
    out: list[dict[str, Any]] = []
    for rid, sc in sorted(rel.items(), key=lambda kv: -abs(float(kv[1]))):
        e = by_id.get(str(rid))
        if not e:
            continue
        out.append(
            {
                "memory_id": str(rid),
                "relationship_strength": round(float(sc), 4),
                "summary": str(e.get("summary") or "")[:260],
                "memory_type": str(e.get("memory_type") or ""),
                "cluster_id": str(e.get("cluster_id") or ""),
                "graph_centrality": float(e.get("graph_centrality") or 0.0),
                "contradiction_resolution_status": str(e.get("contradiction_resolution_status") or ""),
            }
        )
        if len(out) >= max(1, int(limit)):
            break
    return out


def explain_memory_relationships(memory_id: str, *, entries: list[dict] | None = None) -> dict[str, Any]:
    rows = entries if isinstance(entries, list) else fm.entries_snapshot_for_tests()
    by_id = {str(e.get("id") or ""): e for e in rows if e.get("id")}
    mid = str(memory_id or "").strip()
    e = by_id.get(mid)
    if not e:
        return {"status": "error", "detail": "not_found"}
    rel = find_related_memories(mid, limit=12, entries=rows)
    reasons: list[str] = []
    for x in rel[:3]:
        reasons.append(f"{x['memory_id']} (force={x['relationship_strength']})")
    return {
        "status": "ok",
        "memory_id": mid,
        "cluster_id": str(e.get("cluster_id") or ""),
        "graph_degree": int(e.get("graph_degree") or 0),
        "graph_centrality": float(e.get("graph_centrality") or 0.0),
        "concept_tags": list(e.get("concept_tags") or [])[:20],
        "contradiction_resolution_status": str(e.get("contradiction_resolution_status") or ""),
        "top_related": rel,
        "explanation": (
            "cette mémoire est liée à " + ", ".join(reasons)
            if reasons
            else "aucune relation forte détectée"
        ),
    }


def refresh_relationship_graph(*, persist: bool = True) -> dict[str, Any]:
    with _LOCK:
        g = build_memory_relationship_graph()
        rows = g.get("entries") or []
        if persist:
            with fm._STORE_LOCK:  # noqa: SLF001
                fm._save_entries(rows)  # noqa: SLF001
        return {
            "status": "ok",
            "nodes": g.get("nodes"),
            "pairs_evaluated": g.get("pairs_evaluated"),
            "clusters_count": g.get("clusters_count"),
            "persisted": bool(persist),
            "hubs": g.get("hubs") or [],
        }

