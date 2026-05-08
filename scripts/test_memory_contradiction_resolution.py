#!/usr/bin/env python3
"""Memory Contradiction Resolution V11.6 tests.
cd openchawn && .venv/bin/python scripts/test_memory_contradiction_resolution.py
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


def _m(
    eid: str,
    summary: str,
    *,
    mt: str = "project",
    days_ago: int = 4,
    access: int = 1,
    archived: bool = False,
    contradiction: bool = False,
    importance: float = 0.6,
    ltv: float = 0.6,
) -> dict:
    ts = _iso(days_ago)
    return {
        "id": eid,
        "timestamp": ts,
        "created_at": ts,
        "updated_at": ts,
        "last_accessed_at": _iso(max(0, days_ago - 1)),
        "memory_type": mt,
        "memory_level": "summary_memory",
        "project_name": "openchawn",
        "project": "openchawn",
        "summary": summary,
        "user_message": "",
        "assistant_response": "",
        "tags": ["memory", "policy"],
        "access_count": access,
        "importance_score": importance,
        "long_term_value": ltv,
        "graph_centrality": 1.8,
        "contradiction_risk": 0.75 if contradiction else 0.12,
        "contradiction_detected": contradiction,
        "lifecycle_status": "archived" if archived else "active",
        "metadata": {},
    }


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.memory import faiss_memory as fsm
    from app.memory import fractal_memory as fm
    from app.memory import memory_compression as mc
    from app.memory import memory_contradiction_resolution as mcr
    from app.memory import memory_decision_engine as mde

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_contra_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"
    fsm._SEM_DIR = tmp / "semantic"  # type: ignore[attr-defined]
    fsm._FAISS_INDEX_PATH = fsm._SEM_DIR / "faiss.index"  # type: ignore[attr-defined]
    fsm._META_PATH = fsm._SEM_DIR / "faiss_meta.json"  # type: ignore[attr-defined]

    rows = [
        _m("m_old", "Ollama est provider principal en production", days_ago=35, contradiction=True, importance=0.45, ltv=0.35),
        _m("m_new", "Ollama interdit en production; DeepSeek principal via OpenRouter", days_ago=1, contradiction=True, importance=0.85, ltv=0.8),
        _m("m_arch", "Provider alternatif archive", archived=True, contradiction=True, importance=0.9, ltv=0.9),
        _m("m_sec", "api key=sk-secret-123456 security policy", contradiction=True, importance=0.8, ltv=0.8),
        _m("m_norm", "Railway observability stable", contradiction=False, importance=0.7, ltv=0.7),
        _m("m_u1", "same unresolved policy", contradiction=True, importance=0.55, ltv=0.5),
        _m("m_u2", "same unresolved policy", contradiction=True, importance=0.56, ltv=0.51),
        _m("m_dep", "deprecated memory should not be indexed", contradiction=False, importance=0.3, ltv=0.2),
    ]
    rows = [fm._ensure_entry_defaults(dict(e)) for e in rows]  # noqa: SLF001
    fm._save_entries(rows)  # noqa: SLF001

    cands = mcr.detect_resolution_candidates(rows)
    assert any(set(x.get("memory_ids") or []) == {"m_old", "m_new"} and str(x.get("status")) == "conflict_active" for x in cands), cands

    rep = mcr.refresh_contradiction_resolutions(persist=True)
    assert rep.get("status") == "ok", rep

    snap = fm.entries_snapshot_for_tests()
    by = {str(e.get("id")): e for e in snap}
    assert str(by["m_old"].get("contradiction_resolution_status") or "") in ("superseded", "unresolved", "conflict_active")
    assert str(by["m_new"].get("contradiction_resolution_status") or "") in ("resolved", "conflict_active", "unresolved")
    assert str(by["m_sec"].get("contradiction_resolution_status") or "") == "needs_human_review"
    assert bool(by["m_sec"].get("human_review_required")) is True

    # archived should lose arbitration
    sc = mcr.score_conflicting_memories(by["m_arch"], by["m_new"])
    assert str(sc.get("winner_memory_id")) == "m_new", sc

    # unresolved should not be compressed
    by["m_u1"]["contradiction_resolution_status"] = "unresolved"
    by["m_u2"]["contradiction_resolution_status"] = "unresolved"
    comp = mc.apply_compression_in_memory(snap, dry_run=True)
    for cl in (comp.get("created") or []):
        mark = cl.get("would_mark") or []
        assert "m_u1" not in mark and "m_u2" not in mark, comp

    # deprecated should not be indexed in FAISS
    by["m_dep"]["contradiction_resolution_status"] = "deprecated"
    by["m_dep"]["indexable"] = True
    rdep = fsm.add_memory_embedding(by["m_dep"])
    assert str(rdep.get("reason") or "") in ("deprecated", "non_indexable"), rdep

    # decision debug exposes resolution reason
    by["m_old"]["resolution_reason"] = "new production policy supersedes old one"
    bundle = mde.build_memory_decision_bundle(
        query="provider prod policy",
        candidates=[by["m_old"], by["m_new"]],
        entries_snapshot=list(by.values()),
        project_slug="openchawn",
    )
    ddbg = (bundle.get("selected_memories") or [])[0].get("_decision_debug") if (bundle.get("selected_memories") or []) else {}
    assert "resolution_reason" in (ddbg or {}), ddbg

    client = TestClient(app)
    r0 = client.get("/memory/contradictions/candidates")
    assert r0.status_code == 200
    r1 = client.post("/memory/contradictions/refresh")
    assert r1.status_code == 200
    r2 = client.get("/memory/contradictions/report")
    assert r2.status_code == 200
    r3 = client.get("/memory/contradictions/explain/m_new")
    assert r3.status_code == 200
    r4 = client.post(
        "/memory/contradictions/resolve",
        json={"winner_memory_id": "m_new", "loser_memory_id": "m_old", "reason": "manual arbitration", "mode": "manual"},
    )
    assert r4.status_code == 200

    print("OK memory_contradiction_resolution tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

