#!/usr/bin/env python3
"""Smoke tests Memory Compression V11.6 — cd openchawn && .venv/bin/python scripts/test_memory_compression.py"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _base_entry(
    eid: str,
    *,
    seq: int,
    summary: str,
    tags: list[str],
    contradiction: bool = False,
    secret_meta: bool = False,
    memory_level: str = "summary_memory",
) -> dict:
    ts = f"2030-01-{10 + seq:02d}T12:{30 + seq:02d}:00+00:00"
    md: dict = {}
    if secret_meta:
        md["secret"] = True
    return {
        "id": eid,
        "timestamp": ts,
        "memory_type": "project",
        "memory_level": memory_level,
        "project_name": "openchawn",
        "project": "openchawn",
        "user_id": "u_compression",
        "source": "test",
        "user_message": "",
        "assistant_response": "",
        "summary": summary,
        "tags": tags,
        "importance_score": 0.75,
        "parent_id": None,
        "children_ids": [],
        "metadata": md,
        "lifecycle_status": "active",
        "contradiction_detected": contradiction,
    }


def main() -> int:
    from fastapi.testclient import TestClient

    from app.memory import fractal_memory as fm
    from app.memory import memory_compression as mc
    from app.main import app

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_memc_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"

    shared_summary = (
        "OpenChawn: DeepSeek est le provider principal, déploiement Railway documenté pour la prod mémoire."
    )
    tbase = ["openchawn", "deepseek", "railway", "summarizer"]
    trio = [
        _base_entry("mem_src_a001", seq=1, summary=shared_summary, tags=tbase),
        _base_entry("mem_src_a002", seq=2, summary=shared_summary, tags=tbase),
        _base_entry("mem_src_a003", seq=3, summary=shared_summary, tags=tbase),
    ]
    contra = _base_entry(
        "mem_contra_o",
        seq=4,
        summary="Ollama serait encore autorisé en local pour benchmarks OpenChawn selon ancienne hypothèse.",
        tags=tbase,
        contradiction=True,
    )
    secret_one = _base_entry(
        "mem_secret_bad",
        seq=5,
        summary="Configurer api_key=fake_placeholder_test pour démo Railway.",
        tags=tbase + ["danger"],
        secret_meta=True,
    )

    trio[0]["metadata"]["linked_concept_id"] = "concept_stack"
    trio[1]["metadata"]["linked_concept_id"] = "concept_stack"
    trio[2]["metadata"]["linked_concept_id"] = "concept_stack"
    contra["metadata"]["linked_concept_id"] = "concept_stack"

    entries = [*trio, contra, secret_one]
    entries = [fm._ensure_entry_defaults(dict(e)) for e in entries]  # noqa: SLF001
    fm._save_entries(entries)  # noqa: SLF001

    rep_run = mc.run_memory_compression_job(project="openchawn")
    created = rep_run.get("created") or []
    assert created, json.dumps(rep_run, ensure_ascii=False)

    cid = created[0].get("id")
    sources = created[0].get("source_memory_ids") or []
    assert set(sources) >= {"mem_src_a001", "mem_src_a002", "mem_src_a003"}

    fresh = fm.entries_snapshot_for_tests()
    by_id = {str(e["id"]): e for e in fresh}
    comp = by_id[cid]
    assert str(comp.get("memory_type")) == "compressed"
    md_top = comp.get("metadata") if isinstance(comp.get("metadata"), dict) else {}
    assert md_top.get("source_memory_ids")
    refs = md_top.get("contradiction_refs") or []
    assert "mem_contra_o" in refs
    assert "mem_secret_bad" not in md_top.get("source_memory_ids", [])

    for sid in sources:
        m = by_id[sid]
        mum = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
        assert mum.get("compressed_into") == cid

    cand = mc.find_compression_candidates(fresh, include_archived=False)
    assert cand.get("status") == "ok"

    cands_ov = fm.gather_layered_candidates(
        fresh,
        "OpenChawn DeepSeek Railway memory retrieval test",
        user_key="u_compression",
        project_name_hint="openchawn",
        is_guest=False,
        layer_limits={"system": 0, "user": 0, "project": 3, "session": 1},
        compression_level="aggressive",
        contradiction_mode="off",
    )
    proj_hits = [
        x
        for x in cands_ov
        if isinstance(x.get("_retrieval_debug"), dict)
        and "layer:project" in str(x.get("_retrieval_debug", {}).get("why_selected"))
    ]
    assert proj_hits, "couche projet attendue"
    assert str(proj_hits[0].get("memory_type")) == "compressed", proj_hits[0]

    client = TestClient(app)
    r0 = client.get("/memory/compression/candidates")
    assert r0.status_code == 200

    rh = client.get("/memory/compression/health")
    assert rh.status_code == 200
    hb = rh.json()
    assert hb.get("status") == "ok"

    r1 = client.post(
        "/memory/compression/run",
        json={"dry_run": True, "include_archived": False, "project": ""},
    )
    assert r1.status_code == 200

    rget = client.get(f"/memory/compression/{cid}")
    assert rget.status_code == 200
    body = rget.json()
    assert body.get("status") == "ok"
    mem = body.get("memory") or {}
    assert mem.get("memory_type") == "compressed"

    print("OK memory_compression tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
