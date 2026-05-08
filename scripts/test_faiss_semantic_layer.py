#!/usr/bin/env python3
"""FAISS Semantic Layer V11.6 smoke tests.
cd openchawn && .venv/bin/python scripts/test_faiss_semantic_layer.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _base_entry(
    eid: str,
    *,
    summary: str,
    memory_type: str = "project",
    level: str = "summary_memory",
    contradicted: bool = False,
    archived: bool = False,
) -> dict:
    return {
        "id": eid,
        "timestamp": "2031-03-11T10:20:00+00:00",
        "memory_type": memory_type,
        "memory_level": level,
        "project_name": "openchawn",
        "project": "openchawn",
        "user_id": "u_sem",
        "source": "test",
        "user_message": "",
        "assistant_response": "",
        "summary": summary,
        "tags": ["openchawn", "memory"],
        "importance_score": 0.72,
        "parent_id": None,
        "children_ids": [],
        "metadata": {},
        "lifecycle_status": "archived" if archived else "active",
        "access_count": 0,
        "decay_score": 35,
        "contradiction_detected": contradicted,
    }


def _payload_has_secret(payload: object) -> bool:
    s = json.dumps(payload, ensure_ascii=False)
    pats = [
        r"\bBearer\s+[A-Za-z0-9\-\._]+\b",
        r"\bsk-[A-Za-z0-9]{12,}\b",
        r"api_key\s*=\s*[^\s\"']+",
    ]
    return any(re.search(p, s) for p in pats)


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.memory import faiss_memory as fsm
    from app.memory import fractal_memory as fm

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_sem_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"
    fsm._SEM_DIR = tmp / "semantic"  # type: ignore[attr-defined]
    fsm._FAISS_INDEX_PATH = fsm._SEM_DIR / "faiss.index"  # type: ignore[attr-defined]
    fsm._META_PATH = fsm._SEM_DIR / "faiss_meta.json"  # type: ignore[attr-defined]

    entries = [
        _base_entry(
            "mem_fr_1",
            summary="Déploiement OpenChawn sur Railway avec DeepSeek en production mémoire.",
        ),
        _base_entry(
            "mem_en_1",
            summary="OpenChawn memory retrieval remains hybrid with timeline and semantic layer.",
        ),
        _base_entry(
            "mem_contra_1",
            summary="OpenChawn should revert to Ollama in production immediately.",
            contradicted=True,
        ),
        _base_entry(
            "mem_arch_1",
            summary="Archived memory about legacy provider setup.",
            archived=True,
        ),
        _base_entry(
            "mem_secret",
            summary="Set api_key=sk-live-should-never-be-indexed for provider test.",
        ),
    ]
    entries = [fm._ensure_entry_defaults(dict(e)) for e in entries]  # noqa: SLF001
    fm._save_entries(entries)  # noqa: SLF001

    rep = fsm.rebuild_semantic_index()
    assert rep.get("status") == "ok", rep
    assert int(rep.get("vectors_count") or 0) >= 3, rep

    # EN query retrieves FR memory (multilingual bridge).
    en = fsm.search_semantic_memory("How to deploy OpenChawn on Railway with DeepSeek?", top_k=6)
    ids_en = {str(x.get("memory_id")) for x in (en.get("results") or [])}
    assert "mem_fr_1" in ids_en, ids_en
    assert float(en.get("elapsed_ms") or 0.0) >= 0.0
    assert str(en.get("backend") or "") in ("faiss", "bruteforce_fallback")

    # FR query retrieves EN memory.
    fr = fsm.search_semantic_memory("Explique la couche hybride semantic timeline d'OpenChawn", top_k=6)
    ids_fr = {str(x.get("memory_id")) for x in (fr.get("results") or [])}
    assert "mem_en_1" in ids_fr, ids_fr

    # contradiction excluded + archived filtered
    filt = fsm.search_semantic_memory(
        "openchawn production",
        top_k=10,
        filters={"contradicted": False, "archived": False},
    )
    filt_ids = {str(x.get("memory_id")) for x in (filt.get("results") or [])}
    assert "mem_contra_1" not in filt_ids
    assert "mem_arch_1" not in filt_ids

    # rebuild stable
    rep2 = fsm.rebuild_semantic_index()
    assert rep2.get("vectors_count") == rep.get("vectors_count")
    rep3 = fsm.rebuild_semantic_index(incremental=True)
    assert rep3.get("status") == "ok"

    # Hybrid retrieval + dedup
    ctx, mems = fm.build_layered_memory_context(
        "How does OpenChawn deploy on Railway?",
        user_key="user-sem",
        project_name_hint="openchawn",
        is_guest=False,
    )
    assert isinstance(ctx, str) and ctx
    ids = [str(m.get("id")) for m in mems if m.get("id")]
    assert len(ids) == len(set(ids)), "dedup by memory id failed"
    has_semantic = any(
        ("layer:semantic" in str((m.get("_retrieval_debug") or {}).get("why_selected") or ""))
        or ("semantic_match=true" in str((m.get("_retrieval_debug") or {}).get("why_selected") or ""))
        for m in mems
        if isinstance(m.get("_retrieval_debug"), dict)
    )
    assert has_semantic, "hybrid retrieval should include semantic contribution"

    # Endpoint smoke
    client = TestClient(app)
    r0 = client.get("/memory/semantic/stats")
    assert r0.status_code == 200
    st = r0.json()
    assert "updated_at" in st
    assert "max_search_k" in st
    r1 = client.get("/memory/semantic/search", params={"q": "OpenChawn Railway deployment", "limit": 6})
    assert r1.status_code == 200
    rh = client.get("/memory/semantic/health", params={"window": 20})
    assert rh.status_code == 200
    hb = rh.json()
    assert hb.get("status") == "ok"
    assert int(hb.get("events_count") or 0) >= 1
    assert "avg_hit_rate" in hb
    r2 = client.post("/memory/semantic/rebuild", params={"incremental": True})
    assert r2.status_code == 200

    # No secret leak in semantic payloads
    assert not _payload_has_secret(r0.json())
    assert not _payload_has_secret(r1.json())
    assert not _payload_has_secret(rh.json())
    assert not _payload_has_secret(r2.json())

    print("OK faiss_semantic_layer tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

