#!/usr/bin/env python3
"""
Smoke Memory Decision Engine V11.6 (store JSON isolé).
  cd openchawn && .venv/bin/python scripts/test_memory_decision_engine.py
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
    from app.memory import fractal_memory as fm
    from app.memory import memory_decision_engine as mde

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_decision_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    uid = "user-decision-engine-77"

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
        "Sur OpenChawn Ollama est le moteur principal en local pour notre développement quotidien.",
        "Confirmé : Ollama local uniquement.",
    )
    wr(
        "Ollama est interdit sur OpenChawn en production, pas d'usage autorisé là-bas.",
        "OK interdiction Ollama en prod.",
    )

    ctx, mems = fm.build_layered_memory_context(
        "Quel provider pour OpenChawn en production et pourquoi ?",
        user_key=uid,
        project_name_hint="openchawn",
        is_guest=False,
    )
    assert ctx, "context text expected"
    assert mems, mems
    assert all(isinstance(m.get("_decision_debug"), dict) for m in mems), "decision debug missing"

    last = mde.get_last_decision_bundle()
    assert last.get("status") == "ok"
    assert last.get("selected_memories")

    sim = mde.simulate_memory_decision(
        query="provider production OpenChawn",
        project="openchawn",
        user_key=uid,
        is_guest=False,
    )
    assert sim.get("candidate_count", 0) >= 1
    assert sim.get("scoring_breakdown")

    blob = json.dumps(last, ensure_ascii=False).lower()
    assert "sk-" not in blob and "api_key=" not in blob

    # archived synthetic rejection via bundle API
    archived_fake = {
        "id": "mem_arch_test_only",
        "summary": "vieille mémoire faible à rejeter",
        "memory_type": "session",
        "memory_level": "summary_memory",
        "lifecycle_status": fm.MEMORY_LIFECYCLE_ARCHIVED,
        "importance_score": 0.1,
        "decay_score": 90.0,
        "contradiction_detected": False,
        "timestamp": "2020-01-01T00:00:00+00:00",
        "created_at": "2020-01-01T00:00:00+00:00",
        "project_name": "openchawn",
        "user_id": uid,
        "_retrieval_debug": {
            "why_selected": "test",
            "relevance_score": 3,
            "importance_score": 0.1,
            "decay_score": 90.0,
            "memory_type": "session",
            "retrieval_rank": 99,
            "composite_score": 1.0,
        },
    }
    entries = fm.entries_snapshot_for_tests()
    bundle_arch = mde.build_memory_decision_bundle(
        query="test",
        candidates=[archived_fake],
        entries_snapshot=entries,
        project_slug="openchawn",
        capture_last=False,
    )
    rej = bundle_arch.get("rejected_memories") or []
    assert rej and any(not x.get("_decision_debug", {}).get("selected") for x in rej)

    summaries = " ".join(str(m.get("summary") or "").lower() for m in mems)
    assert "deepseek" in summaries

    # scoring_breakdown keys memory_id not summary — compare summaries via simulate selected
    sel_txt = json.dumps(sim.get("selected_memories") or [], ensure_ascii=False).lower()
    assert "deepseek" in sel_txt

    print("OK memory decision engine tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
