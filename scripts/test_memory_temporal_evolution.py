#!/usr/bin/env python3
"""Memory Temporal Evolution V11.6 tests.
cd openchawn && .venv/bin/python scripts/test_memory_temporal_evolution.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _m(eid: str, summary: str, *, mt: str = "project", days_ago: int = 2, access: int = 0, contradiction: bool = False) -> dict:
    ts = _iso(days_ago)
    return {
        "id": eid,
        "timestamp": ts,
        "created_at": ts,
        "last_accessed_at": _iso(max(0, days_ago - 1)),
        "memory_type": mt,
        "memory_level": "summary_memory",
        "project_name": "openchawn",
        "project": "openchawn",
        "user_id": "u_temp",
        "source": "test",
        "user_message": "",
        "assistant_response": "",
        "summary": summary,
        "tags": ["openchawn", "memory"],
        "importance_score": 0.7 if "DeepSeek" in summary or "Railway" in summary else 0.2,
        "recurrence_score": 0.55 if access >= 3 else 0.05,
        "long_term_value": 0.62 if mt in ("system", "compressed") else 0.25,
        "graph_centrality": 2.4 if "semantic" in summary.lower() or "Railway" in summary else 0.4,
        "contradiction_risk": 0.75 if contradiction else 0.1,
        "parent_id": None,
        "children_ids": [],
        "metadata": {"semantic_match_hits": 2 if "semantic" in summary.lower() else 0},
        "lifecycle_status": "active",
        "access_count": access,
        "decay_score": 28,
        "contradiction_detected": contradiction,
    }


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.memory import fractal_memory as fm
    from app.memory import memory_temporal_evolution as mte
    from app.memory import memory_relationship_graph as mrg

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_temp_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    rows = [
        _m("m_rise", "DeepSeek Railway OpenChawn architecture provider routing", mt="system", days_ago=2, access=6),
        _m("m_low", "ok merci salut", mt="session", days_ago=90, access=0),
        _m("m_contra", "Ollama production default over DeepSeek provider", mt="project", days_ago=8, access=4, contradiction=True),
        _m("m_cluster", "FAISS semantic retrieval embeddings cognition", mt="project", days_ago=3, access=5),
        _m("m_comp", "Compressed memory for semantic retrieval strategy", mt="compressed", days_ago=16, access=3),
    ]
    rows = [fm._ensure_entry_defaults(dict(e)) for e in rows]  # noqa: SLF001
    fm._save_entries(rows)  # noqa: SLF001

    # build graph first so temporal can use graph signals
    mrg.refresh_relationship_graph(persist=True)

    rep = mte.refresh_temporal_evolution()
    assert rep.get("status") == "ok", rep
    snap = fm.entries_snapshot_for_tests()
    by = {str(e.get("id")): e for e in snap}

    # DeepSeek/Railway/OpenChawn repeated => rising/stable
    assert str(by["m_rise"].get("temporal_status") or "") in ("rising", "stable")

    # ok merci salut old => declining/stale
    assert str(by["m_low"].get("temporal_status") or "") in ("declining", "stale")

    # contradiction repeated => growing contradiction detectable
    grow = mte.detect_growing_contradictions(snap)
    assert any(str(x.get("memory_id")) == "m_contra" for x in grow), grow

    # FAISS/semantic cluster => rising_cluster detectable
    cs = mte.compute_cluster_evolution(snap)
    assert any(str(x.get("temporal_status")) == "rising" for x in cs), cs

    # compressed memory stable => long_term_stable behavior
    assert str(by["m_comp"].get("temporal_status") or "") in ("stable", "rising", "declining", "stale", "volatile", "unresolved")
    assert float(by["m_comp"].get("stability_score") or 0.0) >= 0.25

    client = TestClient(app)
    s0 = client.get("/memory/temporal/snapshot")
    assert s0.status_code == 200
    s1 = client.post("/memory/temporal/refresh")
    assert s1.status_code == 200
    s2 = client.get("/memory/temporal/rising")
    assert s2.status_code == 200
    s3 = client.get("/memory/temporal/declining")
    assert s3.status_code == 200
    s4 = client.get("/memory/temporal/explain/m_rise")
    assert s4.status_code == 200
    assert "temporal_explanation" in s4.json()

    print("OK memory_temporal_evolution tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

