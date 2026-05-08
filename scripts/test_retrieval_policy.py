#!/usr/bin/env python3
"""Tests Retrieval Policy Layer V11.6 (sans LLM).
   cd openchawn && .venv/bin/python scripts/test_retrieval_policy.py
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
    from app.memory import retrieval_policy as rp
    from app.main import app

    rp.clear_last_retrieval_policy_for_tests()
    cse.clear_last_cognitive_state_for_tests()

    base_lim = rp.DEFAULT_LAYER_LIMITS

    fo = rp.policy_for_cognitive_state("focused")
    assert int(fo["max_project"]) >= int(base_lim["project"])
    assert int(fo["max_session"]) < int(base_lim["session"])

    ov = rp.policy_for_cognitive_state("overloaded")
    assert int(ov["max_session"]) < int(base_lim["session"])

    cx = rp.policy_for_cognitive_state("contradicted", contradiction_level="high")
    assert cx["contradiction_mode"] == "include_flagged"
    assert float(cx["conflict_penalty_scale"]) > 1.2

    ex = rp.policy_for_cognitive_state("exploring")
    assert float(ex["diversity_level"]) > float(fo["diversity_level"])

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_rp_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    uid = "user-rpolicy-404"

    def wr(msg: str, reply: str, proj: str = "openchawn") -> None:
        r = fm.write_exchange(
            source="script",
            user_message=msg,
            assistant_response=reply,
            project=proj,
            user_key=uid,
            project_name_hint=proj,
            is_guest=False,
        )
        assert r.saved, r

    wr("Alpha projet OpenChawn.", "OK.", proj="openchawn")
    wr("Beta autre sujet sandbox.", "OK.", proj="sandbox")

    snap_over = {"state": "overloaded", "pressure_score": 82.0, "contradiction_level": "high", "status": "ok"}
    pol_over = rp.build_retrieval_policy(cognitive_snapshot=snap_over)

    entries = fm.entries_snapshot_for_tests()
    cand_over = rp.apply_retrieval_policy(
        entries,
        "OpenChawn sandbox test",
        policy=pol_over,
        user_key=uid,
        project_name_hint="openchawn",
        is_guest=False,
    )

    snap_focus = {"state": "focused", "pressure_score": 28.0, "contradiction_level": "low", "status": "ok"}
    pol_focus = rp.build_retrieval_policy(cognitive_snapshot=snap_focus)
    cand_focus = rp.apply_retrieval_policy(
        entries,
        "OpenChawn sandbox test",
        policy=pol_focus,
        user_key=uid,
        project_name_hint="openchawn",
        is_guest=False,
    )

    assert len(cand_over) <= len(cand_focus), (len(cand_over), len(cand_focus))

    ctx, mems = fm.build_layered_memory_context(
        "Résumé OpenChawn et sandbox ?",
        user_key=uid,
        project_name_hint="openchawn",
        is_guest=False,
    )
    assert isinstance(ctx, str)
    assert isinstance(mems, list)

    last = rp.get_last_retrieval_policy()
    assert last.get("status") == "ok"
    blob = json.dumps(last, ensure_ascii=False).lower()
    assert "sk-" not in blob and "api_key=" not in blob

    client = TestClient(app)
    r1 = client.get("/memory/retrieval-policy")
    assert r1.status_code == 200
    assert "max_session" in r1.json()

    r2 = client.get("/memory/retrieval-policy/simulate", params={"state": "exploring"})
    assert r2.status_code == 200
    body = r2.json()
    assert body.get("simulate") is True
    assert float(body.get("diversity_level") or 0) >= 0.8

    print("OK retrieval_policy tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
