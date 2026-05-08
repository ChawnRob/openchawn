#!/usr/bin/env python3
"""Memory Importance Scoring V11.6 tests.
cd openchawn && .venv/bin/python scripts/test_memory_importance_scoring.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _entry(eid: str, summary: str, *, memory_type: str = "project", level: str = "summary_memory", contradiction: bool = False) -> dict:
    return {
        "id": eid,
        "timestamp": "2032-02-01T10:00:00+00:00",
        "memory_type": memory_type,
        "memory_level": level,
        "project_name": "openchawn",
        "project": "openchawn",
        "user_id": "u_imp",
        "source": "test",
        "user_message": "",
        "assistant_response": "",
        "summary": summary,
        "tags": ["openchawn", "memory"],
        "importance_score": 0.2,
        "parent_id": None,
        "children_ids": [],
        "metadata": {},
        "lifecycle_status": "active",
        "access_count": 0,
        "decay_score": 30,
        "contradiction_detected": contradiction,
    }


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.memory import faiss_memory as fsm
    from app.memory import fractal_memory as fm
    from app.memory import memory_importance as mi

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_imp_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"
    fsm._SEM_DIR = tmp / "semantic"  # type: ignore[attr-defined]
    fsm._FAISS_INDEX_PATH = fsm._SEM_DIR / "faiss.index"  # type: ignore[attr-defined]
    fsm._META_PATH = fsm._SEM_DIR / "faiss_meta.json"  # type: ignore[attr-defined]

    hi = _entry(
        "m_hi",
        "OpenChawn architecture: DeepSeek provider principal, Railway deployment, security memory policy.",
        memory_type="system",
        level="concept_memory",
    )
    hi["metadata"]["linked_concept_id"] = "c_stack"
    hi["metadata"]["merge_count"] = 4
    hi["access_count"] = 5

    low = _entry("m_low", "ok merci salut", memory_type="session")
    sec = _entry("m_sec", "api_key=sk-live-secret")
    contra = _entry("m_contra", "Ollama should be production default for OpenChawn", contradiction=True)
    comp = _entry("m_comp", "Compressed architecture memory for OpenChawn", memory_type="compressed")
    comp["metadata"]["compression_score"] = 0.8

    rows = [fm._ensure_entry_defaults(dict(x)) for x in (hi, low, sec, contra, comp)]  # noqa: SLF001
    fm._save_entries(rows)  # noqa: SLF001

    r0 = mi.refresh_importance_scores()
    assert r0.get("status") == "ok"
    snap = fm.entries_snapshot_for_tests()
    by = {str(e.get("id")): e for e in snap}

    assert float(by["m_hi"].get("importance_score") or 0.0) >= 0.7
    assert float(by["m_low"].get("importance_score") or 0.0) <= 0.25
    assert float(by["m_sec"].get("importance_score", 1.0)) == 0.0
    assert by["m_sec"].get("indexable") is False
    assert float(by["m_contra"].get("contradiction_risk") or 0.0) >= 0.6
    assert float(by["m_comp"].get("importance_score") or 0.0) >= float(by["m_low"].get("importance_score") or 0.0)
    assert str(by["m_hi"].get("importance_updated_at") or "")

    # refresh updates importance_updated_at
    t0 = str(by["m_hi"].get("importance_updated_at") or "")
    r1 = mi.refresh_importance_scores()
    assert r1.get("status") == "ok"
    by2 = {str(e.get("id")): e for e in fm.entries_snapshot_for_tests()}
    t1 = str(by2["m_hi"].get("importance_updated_at") or "")
    assert t1 and t1 >= t0

    # secret non indexable
    rep_sec = fsm.add_memory_embedding(by2["m_sec"])
    assert rep_sec.get("status") == "ok"
    assert rep_sec.get("added") is False

    client = TestClient(app)
    h = client.get("/memory/importance/health")
    assert h.status_code == 200
    rr = client.post("/memory/importance/refresh")
    assert rr.status_code == 200
    top = client.get("/memory/importance/top", params={"limit": 5})
    assert top.status_code == 200
    ex = client.get("/memory/importance/explain/m_hi")
    assert ex.status_code == 200
    ej = ex.json()
    assert "importance_explanation" in ej and isinstance(ej["importance_explanation"], str)

    print("OK memory_importance_scoring tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

