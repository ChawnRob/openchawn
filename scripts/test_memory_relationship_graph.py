#!/usr/bin/env python3
"""Memory Relationship Graph Layer V11.6 tests.
cd openchawn && .venv/bin/python scripts/test_memory_relationship_graph.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _e(eid: str, summary: str, *, memory_type: str = "project", contradiction: bool = False) -> dict:
    return {
        "id": eid,
        "timestamp": "2032-03-02T12:00:00+00:00",
        "memory_type": memory_type,
        "memory_level": "summary_memory",
        "project_name": "openchawn",
        "project": "openchawn",
        "user_id": "u_graph",
        "source": "test",
        "user_message": "",
        "assistant_response": "",
        "summary": summary,
        "tags": ["openchawn", "memory"],
        "importance_score": 0.5,
        "parent_id": None,
        "children_ids": [],
        "metadata": {},
        "lifecycle_status": "active",
        "access_count": 1,
        "decay_score": 30,
        "contradiction_detected": contradiction,
    }


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.memory import fractal_memory as fm
    from app.memory import graph_persistence as gp
    from app.memory import memory_relationship_graph as mrg

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_graph_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"
    gp._DIR = tmp / "relationship_graph"  # type: ignore[attr-defined]
    gp._GRAPH_PATH = gp._DIR / "graph_snapshot.json"  # type: ignore[attr-defined]

    rows = [
        _e("m_ds", "DeepSeek provider routing strategy for OpenChawn with OpenRouter fallback."),
        _e("m_or", "OpenRouter provider routing for OpenChawn decisions."),
        _e("m_rw", "Railway deployment and observability pipeline for production."),
        _e("m_fa", "FAISS semantic retrieval embeddings cognition index."),
        _e("m_contra", "Ollama should replace DeepSeek in production", contradiction=True),
        _e("m_ok", "ok merci salut", memory_type="session"),
        _e("m_cmp", "Compressed memory for provider strategy and routing", memory_type="compressed"),
    ]
    rows = [fm._ensure_entry_defaults(dict(e)) for e in rows]  # noqa: SLF001
    rows[1]["metadata"]["linked_concept_id"] = "c_provider"
    rows[6]["metadata"]["linked_concept_id"] = "c_provider"
    fm._save_entries(rows)  # noqa: SLF001

    rep = gp.rebuild_relationship_graph(persist_entries=True)
    assert rep.get("status") == "ok", rep
    snap = fm.entries_snapshot_for_tests()
    by = {str(e.get("id")): e for e in snap}

    # clusters OpenChawn/Railway/FAISS detected
    assert str(by["m_rw"].get("cluster_id") or "").startswith("cluster_")
    assert str(by["m_fa"].get("cluster_id") or "").startswith("cluster_")

    # contradiction creates negative relation
    rels = by["m_contra"].get("relationship_strengths") if isinstance(by["m_contra"].get("relationship_strengths"), dict) else {}
    assert any(float(v) < 0 for v in rels.values()), rels

    # central concept hubs detected
    hubs = mrg.detect_concept_hubs(snap, mrg.link_related_memories(snap).get("relationships") or {})
    assert hubs and float(hubs[0].get("centrality") or 0.0) >= 0.0

    # retrieval enrich via graph centrality field
    ctx, mems = fm.build_layered_memory_context("provider routing deepseek openrouter", user_key="u_graph", project_name_hint="openchawn", is_guest=False)
    assert isinstance(ctx, str)
    assert any("graph_centrality" in (m.get("_retrieval_debug") or {}) for m in mems if isinstance(m.get("_retrieval_debug"), dict))

    # compressed memories keep relations
    assert len(by["m_cmp"].get("related_memory_ids") or []) >= 1

    # rebuild stable
    rep2 = gp.rebuild_relationship_graph(persist_entries=True)
    assert rep2.get("nodes") == rep.get("nodes")

    client = TestClient(app)
    s = client.get("/memory/graph/stats")
    assert s.status_code == 200
    h = client.get("/memory/graph/hubs")
    assert h.status_code == 200
    r = client.get("/memory/graph/related/m_ds")
    assert r.status_code == 200
    rb = client.post("/memory/graph/rebuild")
    assert rb.status_code == 200
    ex = client.get("/memory/graph/explain/m_ds")
    assert ex.status_code == 200
    assert "explanation" in ex.json()

    print("OK memory_relationship_graph tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

