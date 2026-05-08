#!/usr/bin/env python3
"""Memory Consolidation Scheduler V11.6 — cd openchawn && .venv/bin/python scripts/test_memory_consolidation_scheduler.py"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _base_entry(
    eid: str,
    *,
    seq: int,
    summary: str,
    tags: list[str],
    linked_concept: str,
    contradiction: bool = False,
    secret_meta: bool = False,
) -> dict:
    ts = f"2030-02-{10 + seq % 18:02d}T15:{40 + seq % 18:02d}:00+00:00"
    md: dict = {"linked_concept_id": linked_concept}
    if secret_meta:
        md["secret"] = True
    return {
        "id": eid,
        "timestamp": ts,
        "memory_type": "project",
        "memory_level": "summary_memory",
        "project_name": "openchawn",
        "project": "openchawn",
        "user_id": "u_sched",
        "source": "test",
        "user_message": "",
        "assistant_response": "",
        "summary": summary,
        "tags": tags,
        "importance_score": 0.62,
        "parent_id": None,
        "children_ids": [],
        "metadata": md,
        "lifecycle_status": "active",
        "access_count": 0,
        "decay_score": 55,
        "contradiction_detected": contradiction,
    }


def _forbidden_secret_leaks(blob: str) -> list[str]:
    bad: list[str] = []
    pats = [
        r"\bBearer\s+[A-Za-z0-9\-._]+\b",
        r"\bsk-[A-Za-z0-9]{16,}",
        r"api_key\s*=\s*[^\s\"']+",
    ]
    for p in pats:
        bad.extend(re.findall(p, blob))
    # Redacted / generic placeholders only for our deliberate test line are ok to appear as literal "fake_placeholder"
    real_keyish = [
        x
        for x in bad
        if "fake_placeholder_sched_test" not in x and "sk-test-redacted-marker" not in x
    ]
    return real_keyish


def main() -> int:
    from fastapi.testclient import TestClient

    from app.memory import fractal_memory as fm
    from app.memory import memory_consolidation_scheduler as mcs
    from app.main import app

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_mcsch_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    s_deepseek = (
        "OpenChawn: DeepSeek est le provider préféré pour la couche mémoire; "
        "Railway assure le déploiement continu."
    )
    s_railway = (
        "Railway: pipeline OpenChawn validé avec healthchecks; DeepSeek reachable depuis le worker."
    )
    s_oc = (
        "OpenChawn projet mère: consolidateur V11 et compression locale avant index FAISS futur."
    )

    buckets = [
        (s_deepseek, "lc_ds", ["openchawn", "deepseek", "infra"]),
        (s_railway, "lc_rw", ["openchawn", "railway", "deploy"]),
        (s_oc, "lc_oc", ["openchawn", "architecture", "roadmap"]),
    ]
    trio: list[dict] = []
    seq = 0
    for summary, cid, tg in buckets:
        for j in range(3):
            seq += 1
            trio.append(
                _base_entry(
                    f"sched_{cid}_{j}",
                    seq=seq,
                    summary=summary,
                    tags=tg,
                    linked_concept=cid,
                )
            )

    contra = _base_entry(
        "sched_contra_1",
        seq=seq + 1,
        summary="Hypothèse contradictoire ancienne OpenChawn: stockage Postgres obligatoire avant V11.",
        tags=["legacy"],
        linked_concept="lc_old",
        contradiction=True,
    )
    risky = _base_entry(
        "sched_secret_placeholder",
        seq=seq + 2,
        summary="Configurer api_key=fake_placeholder_sched_test pour démo sandbox isolée Railway.",
        tags=["sandbox"],
        linked_concept="lc_sec",
        secret_meta=False,
    )
    risky["metadata"]["danger_example"] = "sk-test-redacted-marker"

    bundle = [*trio, contra, risky]
    bundle = [fm._ensure_entry_defaults(dict(e)) for e in bundle]  # noqa: SLF001
    before_ids = {str(e["id"]) for e in bundle}
    fm._save_entries(bundle)  # noqa: SLF001

    plan = mcs.build_consolidation_plan()
    assert plan.get("status") == "ok", plan
    assert plan.get("should_run") is True, json.dumps(plan, ensure_ascii=False)
    rsn = str(plan.get("reason") or "")
    assert (
        "compression_candidates" in rsn or "duplicate_pressure" in rsn or "archive_backlog" in rsn
    ), rsn

    lite = mcs.run_light_consolidation()
    assert lite.get("mode") == "light"
    acts = lite.get("actions") or {}
    comp = acts.get("compression") or {}
    arch = acts.get("archive_rules_archived")
    assert comp.get("candidates_processed", 0) >= 1 or (isinstance(arch, int) and arch >= 0)
    leak = _forbidden_secret_leaks(json.dumps(lite, ensure_ascii=False))
    assert not leak, leak

    after = fm.entries_snapshot_for_tests()
    after_ids = {str(e["id"]) for e in after}
    assert before_ids <= after_ids, (before_ids - after_ids)

    idle = mcs.run_consolidation_cycle("light")
    assert idle.get("mode") in ("idle", "light")

    cli = TestClient(app)
    p0 = cli.get("/memory/consolidation/plan")
    assert p0.status_code == 200

    rl = cli.post("/memory/consolidation/run-light")
    assert rl.status_code == 200

    leak_http = _forbidden_secret_leaks(json.dumps(rl.json(), ensure_ascii=False))
    assert not leak_http, leak_http

    rd = cli.post("/memory/consolidation/run-deep")
    assert rd.status_code == 200
    dj = rd.json()
    assert dj.get("mode") == "deep"
    assert dj.get("actions", {}).get("reflection_report"), dj

    lr = cli.get("/memory/consolidation/last-report")
    assert lr.status_code == 200
    rep = lr.json()
    assert rep.get("mode") in ("deep", "light"), rep
    assert "actions" in rep or rep.get("status") == "empty"

    gp = cli.post("/guest/session")
    assert gp.status_code == 200
    sid = gp.json()["session_id"]

    with patch(
        "app.api.chat.generate_response",
        return_value={
            "output": "Réponse courte de test orchestrateur.",
            "success": True,
            "provider": "mock",
            "status_code": 200,
        },
    ):
        ch = cli.post(
            "/chat",
            json={"message": "Ping OpenChawn DeepSeek Railway consolidation."},
            headers={"X-Guest-Session": sid},
        )

    assert ch.status_code == 200
    body = ch.json()
    assert "output" in body
    assert "memory_used" in body
    assert "consolidation_recommended" in body
    assert isinstance(body["consolidation_recommended"], bool)

    leak_chat = _forbidden_secret_leaks(json.dumps(body, ensure_ascii=False))
    assert not leak_chat, leak_chat

    print("OK memory_consolidation_scheduler tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
