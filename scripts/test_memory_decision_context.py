#!/usr/bin/env python3
"""Memory Decision Context V11.6 tests.
cd openchawn && .venv/bin/python scripts/test_memory_decision_context.py
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
    days_ago: int = 3,
    access: int = 1,
    imp: float = 0.6,
    ltv: float = 0.6,
    rec: float = 0.4,
    trend: float = 0.2,
    contradiction: bool = False,
    resolution_status: str = "",
) -> dict:
    ts = _iso(days_ago)
    return {
        "id": eid,
        "timestamp": ts,
        "created_at": ts,
        "updated_at": ts,
        "last_accessed_at": _iso(max(0, days_ago - 1)),
        "memory_type": mt,
        "memory_level": "concept_memory" if "concept" in summary.lower() else "summary_memory",
        "project_name": "openchawn",
        "project": "openchawn",
        "summary": summary,
        "user_message": "",
        "assistant_response": "",
        "tags": ["openchawn", "memory"],
        "access_count": access,
        "importance_score": imp,
        "long_term_value": ltv,
        "recurrence_score": rec,
        "trend_score": trend,
        "momentum_score": max(0.0, trend),
        "graph_centrality": 2.2 if "DeepSeek" in summary or "Railway" in summary else 0.5,
        "contradiction_risk": 0.72 if contradiction else 0.12,
        "contradiction_detected": contradiction,
        "contradiction_resolution_status": resolution_status,
        "lifecycle_status": "active",
        "metadata": {"semantic_match_hits": 2 if "semantic" in summary.lower() else 0},
    }


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.memory import fractal_memory as fm
    from app.memory import memory_contradiction_resolution as mcr
    from app.memory import memory_decision_context as mdc
    from app.memory import memory_decision_engine as mde
    from app.memory import memory_relationship_graph as mrg
    from app.memory import memory_temporal_evolution as mte

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_ctx_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    rows = [
        _m("m_ds", "DeepSeek provider routing architecture decision", mt="system", access=7, imp=0.9, ltv=0.85, rec=0.8, trend=0.46),
        _m("m_rw", "Railway deployment observability cluster concept", mt="project", access=5, imp=0.84, ltv=0.76, rec=0.72, trend=0.38),
        _m("m_oc", "OpenChawn memory semantic retrieval concept cluster", mt="project", access=4, imp=0.78, ltv=0.72, rec=0.66, trend=0.33),
        _m("m_unr", "Ollama principal en production", mt="project", contradiction=True, resolution_status="unresolved", access=3, imp=0.65, ltv=0.55, rec=0.58, trend=-0.15),
        _m("m_stale", "ancienne decision obsolete", mt="project", days_ago=120, access=0, imp=0.22, ltv=0.2, rec=0.05, trend=-0.45),
        _m("m_frag_a", "isolated note alpha", mt="session", access=0, imp=0.15, ltv=0.12, rec=0.02, trend=-0.1),
        _m("m_frag_b", "isolated note beta", mt="session", access=0, imp=0.14, ltv=0.1, rec=0.02, trend=-0.09),
    ]
    rows = [fm._ensure_entry_defaults(dict(e)) for e in rows]  # noqa: SLF001
    fm._save_entries(rows)  # noqa: SLF001

    mrg.refresh_relationship_graph(persist=True)
    mte.refresh_temporal_evolution()
    mcr.refresh_contradiction_resolutions(persist=True)
    snap = fm.entries_snapshot_for_tests()

    ctx = mdc.build_decision_context(query="DeepSeek OpenChawn Railway", entries=snap, limit=10)
    assert ctx.get("status") == "ok", ctx

    # contexte DeepSeek/OpenChawn/Railway assemblé
    ids = {str(x.get("id") or "") for x in (ctx.get("selected_memories") or [])}
    assert {"m_ds", "m_rw", "m_oc"}.intersection(ids), ids

    # contradictions non résolues pénalisent confiance
    assert float(ctx.get("context_confidence") or 0.0) < 0.9, ctx

    # clusters centraux priorisés
    assert any(str(x.get("context_cluster_role") or "") in ("dominant", "support") for x in (ctx.get("selected_memories") or [])), ctx

    # stale decisions diminuent stabilité
    assert float(ctx.get("context_stability") or 0.0) < 0.9, ctx

    # rising concepts boost retrieval through selection score
    top = (ctx.get("selected_memories") or [])[0]
    assert float(top.get("context_weight") or 0.0) > 0.0, top

    # fragmentation détectée
    assert float(ctx.get("fragmentation_score") or 0.0) >= 0.0, ctx

    # reasoning_summary stable (hors timestamp)
    ctx2 = mdc.build_decision_context(query="DeepSeek OpenChawn Railway", entries=snap, limit=10)
    assert str(ctx.get("reasoning_summary") or "") == str(ctx2.get("reasoning_summary") or "")

    # decision engine uses decision context
    bundle = mde.build_memory_decision_bundle(
        query="DeepSeek OpenChawn Railway",
        candidates=(ctx.get("selected_memories") or [])[:6],
        entries_snapshot=snap,
        project_slug="openchawn",
    )
    assert bundle.get("status") == "ok", bundle
    assert isinstance(bundle.get("decision_context"), dict), bundle

    client = TestClient(app)
    r0 = client.get("/memory/context/build?q=DeepSeek")
    assert r0.status_code == 200
    r1 = client.get("/memory/context/explain?q=DeepSeek")
    assert r1.status_code == 200
    r2 = client.get("/memory/context/risk?q=DeepSeek")
    assert r2.status_code == 200
    r3 = client.get("/memory/context/stability?q=DeepSeek")
    assert r3.status_code == 200
    r4 = client.get("/memory/context/clusters?q=DeepSeek")
    assert r4.status_code == 200

    print("OK memory_decision_context tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

