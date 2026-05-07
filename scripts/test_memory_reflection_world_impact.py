#!/usr/bin/env python3
"""
Smoke Memory Reflection Engine + World Impact Layer MVP (store isolé).
  cd openchawn && .venv/bin/python scripts/test_memory_reflection_world_impact.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_no_secret_leak(blob: str) -> None:
    lower = blob.lower()
    assert "sk-" not in lower and "api_key=" not in lower


def main() -> int:
    from fastapi.testclient import TestClient

    from app.memory import fractal_memory as fm
    from app.memory import memory_decision_engine as mde
    from app.decision import consequence_predictor as cp

    mde.clear_decision_history_for_tests()
    cp.clear_last_impact_for_tests()

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_reflect_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    from app.main import app

    uid = "user-reflection-882"

    def wr(msg: str, reply: str) -> None:
        r = fm.write_exchange(
            source="script",
            user_message=msg,
            assistant_response=reply,
            project="openchawn",
            user_key=uid,
            project_name_hint="openchawn",
            is_guest=False,
        )
        assert r.saved, r

    wr(
        "Pour OpenChawn DeepSeek doit rester le provider LLM principal en production Railway.",
        "Confirmé : DeepSeek principal pour OpenChawn.",
    )
    wr(
        "Sur OpenChawn Ollama est interdit en production Railway, aucune exception.",
        "OK interdiction Ollama en prod.",
    )

    fm.build_layered_memory_context(
        "Quel provider LLM pour OpenChawn sur Railway ?",
        user_key=uid,
        project_name_hint="openchawn",
        is_guest=False,
    )
    fm.build_layered_memory_context(
        "Rappelle la politique OpenChawn prod vs Ollama.",
        user_key=uid,
        project_name_hint="openchawn",
        is_guest=False,
    )

    hist_blob = json.dumps(mde.get_decision_history(), ensure_ascii=False).lower()
    assert "ollama" in hist_blob or "provider" in hist_blob

    from app.memory import memory_reflection_engine as mref

    rep = mref.build_reflection_report()
    assert rep.get("status") == "ok"
    stab = float(rep.get("cognitive_stability_score") or -1)
    assert 0 <= stab <= 100
    assert isinstance(rep.get("optimization_recommendations"), list)
    assert len(rep.get("optimization_recommendations") or []) >= 1

    impact = cp.build_impact_report(
        proposed_action="Activer PostgreSQL pour la mémoire",
        project="openchawn",
        related_memories=[],
        decision_context=mde.get_last_decision_bundle(),
    )
    assert impact.get("likely_benefits")
    assert impact.get("likely_risks")
    for key in (
        "technical_impact",
        "cost_impact",
        "stability_impact",
        "security_impact",
        "memory_impact",
    ):
        assert str(impact.get(key) or "").strip(), key

    leak = json.dumps({**rep, **impact}, ensure_ascii=False)
    assert_no_secret_leak(leak)

    bad = cp.build_impact_report(
        proposed_action="sk-invalidtoken999abcdef_rotatie",
        project="openchawn",
        related_memories=[],
        decision_context=None,
    )
    preview = str(bad.get("proposed_action_preview") or "")
    assert "sk-" not in preview.lower()

    client = TestClient(app)
    rr = client.get("/memory/reflection/report")
    assert rr.status_code == 200
    body = rr.json()
    assert "cognitive_stability_score" in body

    pr = client.post(
        "/decision/predict-consequences",
        json={"proposed_action": "Activer PostgreSQL pour la mémoire persistante", "project": "openchawn"},
    )
    assert pr.status_code == 200
    pj = pr.json()
    assert pj.get("likely_benefits") and pj.get("likely_risks")

    li = client.get("/decision/last-impact")
    assert li.status_code == 200
    assert li.json().get("status") == "ok"

    assert_no_secret_leak(json.dumps(rr.json(), ensure_ascii=False) + json.dumps(li.json(), ensure_ascii=False))

    print("OK reflection + world impact tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
