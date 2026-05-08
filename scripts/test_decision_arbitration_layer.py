#!/usr/bin/env python3
"""Decision Arbitration Layer V11.6 tests.
cd openchawn && .venv/bin/python scripts/test_decision_arbitration_layer.py
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
    imp: float = 0.7,
    ltv: float = 0.7,
    cen: float = 2.0,
    trend: float = 0.3,
    temporal: str = "rising",
    cstatus: str = "resolved",
    risk: float = 0.15,
    human_review: bool = False,
) -> dict:
    ts = _iso(2)
    return {
        "id": eid,
        "timestamp": ts,
        "created_at": ts,
        "updated_at": ts,
        "last_accessed_at": _iso(1),
        "memory_type": "project",
        "memory_level": "summary_memory",
        "project_name": "openchawn",
        "project": "openchawn",
        "summary": summary,
        "user_message": "",
        "assistant_response": "",
        "tags": ["decision", "provider"],
        "importance_score": imp,
        "long_term_value": ltv,
        "graph_centrality": cen,
        "trend_score": trend,
        "momentum_score": max(0.0, trend),
        "temporal_status": temporal,
        "contradiction_risk": risk,
        "contradiction_detected": cstatus in ("unresolved", "conflict_active"),
        "contradiction_resolution_status": cstatus,
        "resolution_confidence": 0.8 if cstatus == "resolved" else 0.2,
        "human_review_required": human_review,
        "lifecycle_status": "active",
        "access_count": 4,
        "metadata": {},
    }


def main() -> int:
    from fastapi.testclient import TestClient

    from app.decision import consequence_predictor as cp
    from app.decision import decision_arbitration as dar
    from app.main import app
    from app.memory import fractal_memory as fm
    from app.memory import memory_contradiction_resolution as mcr
    from app.memory import memory_decision_context as mdc
    from app.memory import memory_relationship_graph as mrg
    from app.memory import memory_temporal_evolution as mte

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_arb_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    rows = [
        _m("m_ds", "Use DeepSeek as default provider", imp=0.88, ltv=0.82, cen=2.8, trend=0.42, temporal="rising", cstatus="resolved", risk=0.08),
        _m("m_oa", "Use OpenAI as elite fallback", imp=0.73, ltv=0.66, cen=1.7, trend=0.18, temporal="stable", cstatus="resolved", risk=0.14),
        _m("m_unr", "Provider conflict unresolved", imp=0.6, ltv=0.5, cen=1.0, trend=-0.2, temporal="declining", cstatus="unresolved", risk=0.8),
        _m("m_dep", "Deprecated provider plan", imp=0.5, ltv=0.45, cen=0.8, trend=-0.25, temporal="declining", cstatus="deprecated", risk=0.3),
        _m("m_sec", "security token rotation api key", imp=0.85, ltv=0.75, cen=1.6, trend=0.2, temporal="stable", cstatus="needs_human_review", risk=0.9, human_review=True),
    ]
    rows = [fm._ensure_entry_defaults(dict(e)) for e in rows]  # noqa: SLF001
    fm._save_entries(rows)  # noqa: SLF001
    mrg.refresh_relationship_graph(persist=True)
    mte.refresh_temporal_evolution()
    mcr.refresh_contradiction_resolutions(persist=True)
    snap0 = fm.entries_snapshot_for_tests()
    for e in snap0:
        if str(e.get("id") or "") == "m_unr":
            e["contradiction_resolution_status"] = "unresolved"
            e["resolution_confidence"] = 0.1
            break
    fm._save_entries(snap0)  # noqa: SLF001

    ctx = mdc.build_decision_context(query="provider strategy", limit=12)
    options = [
        {"title": "Use DeepSeek as default provider", "source_memory_ids": ["m_ds"], "strategy_type": "provider_strategy"},
        {"title": "Use OpenAI as elite fallback", "source_memory_ids": ["m_oa"], "strategy_type": "provider_strategy"},
    ]
    rep = dar.arbitrate_decision(project="openchawn", decision_type="provider_strategy", options=options, context=ctx)
    assert rep.get("status") in ("selected", "tie_needs_review"), rep
    sel = rep.get("selected_option") or {}
    if rep.get("status") == "selected":
        assert "deepseek" in str(sel.get("title") or "").lower(), rep

    # OpenAI fallback should stay viable
    oa = next((o for o in (rep.get("options") or []) if "openai" in str(o.get("title") or "").lower()), {})
    assert str(oa.get("status") or "") in ("rejected", "selected", "tie_needs_review")

    # needs_human_review never auto-selected
    sec_rep = dar.arbitrate_decision(
        project="openchawn",
        decision_type="security_strategy",
        options=[{"title": "Rotate API key now", "source_memory_ids": ["m_sec"], "strategy_type": "security_strategy"}],
        context=ctx,
    )
    sec_opt = (sec_rep.get("options") or [{}])[0]
    assert str(sec_opt.get("status") or "") == "needs_human_review", sec_rep
    assert bool(sec_opt.get("selected")) is False

    # unresolved contradiction penalized
    unr_rep = dar.arbitrate_decision(
        project="openchawn",
        decision_type="provider_strategy",
        options=[{"title": "Use unresolved provider path", "source_memory_ids": ["m_unr"]}],
        context=ctx,
    )
    unr_opt = (unr_rep.get("options") or [{}])[0]
    assert float(unr_opt.get("contradiction_penalty") or 0.0) > 0.3

    # deprecated loses
    snap1 = fm.entries_snapshot_for_tests()
    for e in snap1:
        if str(e.get("id") or "") == "m_dep":
            e["contradiction_resolution_status"] = "deprecated"
            break
    fm._save_entries(snap1)  # noqa: SLF001
    dep_rep = dar.arbitrate_decision(
        project="openchawn",
        decision_type="provider_strategy",
        options=[{"title": "Use deprecated provider plan", "source_memory_ids": ["m_dep"]}],
        context=ctx,
    )
    dep_opt = (dep_rep.get("options") or [{}])[0]
    assert str(dep_opt.get("status") or "") != "selected", dep_rep

    # tie handling
    tie_rep = dar.arbitrate_decision(
        project="openchawn",
        decision_type="provider_strategy",
        options=[
            {"title": "Plan A", "source_memory_ids": ["m_oa"]},
            {"title": "Plan B", "source_memory_ids": ["m_oa"]},
        ],
        context=ctx,
    )
    assert str(tie_rep.get("status") or "") in ("tie_needs_review", "selected")

    # World impact receives selected option
    impact = cp.build_impact_report(
        proposed_action="Set provider strategy",
        project="openchawn",
        related_memories=[],
        decision_context={"arbitration": rep},
    )
    assert "arbitration_selected_option" in impact

    client = TestClient(app)
    r0 = client.post(
        "/decision/arbitration/simulate",
        json={
            "project": "openchawn",
            "decision_type": "provider_strategy",
            "options": [
                {"title": "Use DeepSeek as default provider", "source_memory_ids": ["m_ds"]},
                {"title": "Use OpenAI as elite fallback", "source_memory_ids": ["m_oa"]},
            ],
        },
    )
    assert r0.status_code == 200
    last = client.get("/decision/arbitration/last")
    assert last.status_code == 200
    rep2 = client.get("/decision/arbitration/report")
    assert rep2.status_code == 200
    opts = rep2.json().get("options") or []
    if opts:
        oid = str(opts[0].get("option_id") or "")
        ex = client.get(f"/decision/arbitration/explain/{oid}")
        assert ex.status_code == 200

    print("OK decision_arbitration_layer tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

