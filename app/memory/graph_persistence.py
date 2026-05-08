"""
Graph persistence helpers V11.6.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.memory import fractal_memory as fm
from app.memory import memory_relationship_graph as mrg

_DIR = Path("data/memory/relationship_graph")
_GRAPH_PATH = _DIR / "graph_snapshot.json"


def _ensure() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)


def save_relationship_graph(graph_payload: dict[str, Any]) -> dict[str, Any]:
    _ensure()
    payload = dict(graph_payload or {})
    payload["saved_at"] = time.time()
    _GRAPH_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "path": str(_GRAPH_PATH)}


def load_relationship_graph() -> dict[str, Any]:
    if not _GRAPH_PATH.exists():
        return {"status": "empty", "path": str(_GRAPH_PATH)}
    try:
        return json.loads(_GRAPH_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "error", "detail": str(e), "path": str(_GRAPH_PATH)}


def rebuild_relationship_graph(*, persist_entries: bool = True) -> dict[str, Any]:
    rep = mrg.refresh_relationship_graph(persist=persist_entries)
    rows = fm.entries_snapshot_for_tests()
    hubs = rep.get("hubs") or []
    payload = {
        "status": "ok",
        "nodes": rep.get("nodes"),
        "pairs_evaluated": rep.get("pairs_evaluated"),
        "clusters_count": rep.get("clusters_count"),
        "hubs": hubs,
        "sample_nodes": [
            {
                "id": e.get("id"),
                "cluster_id": e.get("cluster_id"),
                "graph_degree": e.get("graph_degree"),
                "graph_centrality": e.get("graph_centrality"),
                "concept_tags": (e.get("concept_tags") or [])[:12],
            }
            for e in rows[:120]
        ],
        "persist_entries": bool(persist_entries),
    }
    save_relationship_graph(payload)
    return payload


def graph_stats() -> dict[str, Any]:
    rows = fm.entries_snapshot_for_tests()
    if not rows:
        return {"status": "ok", "nodes": 0, "clusters_count": 0, "avg_degree": 0.0, "avg_centrality": 0.0}
    clusters = {str(e.get("cluster_id") or "") for e in rows if str(e.get("cluster_id") or "")}
    degs = [int(e.get("graph_degree") or 0) for e in rows]
    cens = [float(e.get("graph_centrality") or 0.0) for e in rows]
    hubs = sorted(
        [{"id": e.get("id"), "summary": str(e.get("summary") or "")[:180], "centrality": float(e.get("graph_centrality") or 0.0)} for e in rows],
        key=lambda x: float(x["centrality"]),
        reverse=True,
    )[:12]
    return {
        "status": "ok",
        "nodes": len(rows),
        "clusters_count": len(clusters),
        "avg_degree": round(sum(degs) / max(1, len(degs)), 3),
        "avg_centrality": round(sum(cens) / max(1, len(cens)), 4),
        "top_hubs": hubs,
        "snapshot_path": str(_GRAPH_PATH),
        "snapshot_exists": _GRAPH_PATH.exists(),
    }

