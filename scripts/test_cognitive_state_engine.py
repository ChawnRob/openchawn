#!/usr/bin/env python3
"""Smoke Cognitive State Engine V11.6 (sans LLM).
   cd openchawn && .venv/bin/python scripts/test_cognitive_state_engine.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.cognition import cognitive_state_engine as cse
    from app.memory import fractal_memory as fm
    from app.memory import memory_decision_engine as mde
    from app.main import app

    cse.clear_last_cognitive_state_for_tests()
    mde.clear_decision_history_for_tests()

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_cognitive_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    uid = "user-cognitive-901"

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

    wr("OpenChawn utilise DeepSeek en production Railway.", "OK.")
    wr("Ollama reste local uniquement pour le dev.", "OK.")

    ctx, mems = fm.build_layered_memory_context(
        "Quelle stack LLM pour OpenChawn ?",
        user_key=uid,
        project_name_hint="openchawn",
        is_guest=False,
    )
    assert isinstance(ctx, str)
    assert isinstance(mems, list)

    snap = cse.get_last_cognitive_state()
    assert snap.get("status") == "ok"
    ps = float(snap.get("pressure_score") or -1)
    assert 0 <= ps <= 100
    assert str(snap.get("state") or "") in cse.ALLOWED_STATES

    overloaded_flag, rh = cse.detect_context_overload(30)
    assert overloaded_flag and "broad" in rh

    mods = cse.memory_modifiers_for_retrieval_pass(30)
    assert "max_layer_override" in mods and "conflict_penalty_scale" in mods

    client = TestClient(app)
    for path in ("/cognition/state", "/cognition/pressure", "/cognition/focus"):
        r = client.get(path)
        assert r.status_code == 200
        b = r.json()
        assert "pressure_score" in b and "state" in b
        assert 0 <= float(b["pressure_score"]) <= 100

    blob = json.dumps(snap, ensure_ascii=False).lower()
    assert "sk-" not in blob and "api_key=" not in blob

    pressure = cse.compute_cognitive_pressure(
        metrics={
            "contradiction_level": "high",
            "active_memories": 120,
            "average_decay_score": 55.0,
            "reflection_decay_avg": 40.0,
            "reflection_conflict_rate": 2.0,
            "memory_health_label": "fragmented",
            "graph_pairs": 6,
            "dominant_project_share": None,
            "provider_stability": "degraded",
            "retrieval_overload_hint": True,
            "retrieval_health": "retrieval_very_broad",
        },
        candidate_count=30,
    )
    assert pressure >= 70.0

    state = cse.compute_cognitive_state(
        pressure=pressure,
        metrics={
            "contradiction_level": "high",
            "memory_health_label": "good",
            "retrieval_health": "retrieval_very_broad",
            "provider_stability": "degraded",
            "dominant_project_share": None,
            "project_entropy_norm": 0.1,
        },
    )
    assert state in cse.ALLOWED_STATES

    focus = cse.detect_primary_focus(
        reflection_agg={"projects_seen": {"openchawn": 3}},
        live_bundle={"project_slug": "openchawn"},
    )
    assert focus.get("primary_project")

    print("OK cognitive_state_engine tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
