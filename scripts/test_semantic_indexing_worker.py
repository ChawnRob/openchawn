#!/usr/bin/env python3
"""Semantic Indexing Worker + Embedding Cache V11.6 tests.
cd openchawn && .venv/bin/python scripts/test_semantic_indexing_worker.py
"""

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


def _entry(eid: str, summary: str) -> dict:
    return {
        "id": eid,
        "timestamp": "2032-01-01T10:00:00+00:00",
        "memory_type": "project",
        "memory_level": "summary_memory",
        "project_name": "openchawn",
        "project": "openchawn",
        "user_id": "u_worker",
        "source": "test",
        "user_message": "",
        "assistant_response": "",
        "summary": summary,
        "tags": ["openchawn", "semantic"],
        "importance_score": 0.7,
        "parent_id": None,
        "children_ids": [],
        "metadata": {},
        "lifecycle_status": "active",
        "access_count": 0,
        "decay_score": 33,
        "contradiction_detected": False,
    }


def _has_secret(payload: object) -> bool:
    s = json.dumps(payload, ensure_ascii=False)
    return bool(re.search(r"sk-[A-Za-z0-9]{10,}|Bearer\s+[A-Za-z0-9._-]+|api_key\s*=", s))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.memory import embedding_cache as ec
    from app.memory import faiss_memory as fsm
    from app.memory import fractal_memory as fm
    from app.memory import semantic_indexing_worker as siw

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_sem_worker_"))
    fm.STORE_PATH = tmp / "fractal_memory.json"
    fsm._SEM_DIR = tmp / "semantic"  # type: ignore[attr-defined]
    fsm._FAISS_INDEX_PATH = fsm._SEM_DIR / "faiss.index"  # type: ignore[attr-defined]
    fsm._META_PATH = fsm._SEM_DIR / "faiss_meta.json"  # type: ignore[attr-defined]
    ec._CACHE_PATH = tmp / "semantic" / "embedding_cache.json"  # type: ignore[attr-defined]

    siw.clear_semantic_queue_for_tests()
    fm._save_entries([fm._ensure_entry_defaults(_entry("m_a", "OpenChawn deploy Railway DeepSeek"))])  # noqa: SLF001

    # write memory adds job
    enq = siw.enqueue_semantic_index_job("m_a")
    assert enq.get("status") == "ok"
    st0 = siw.get_semantic_worker_status()
    assert int(st0.get("pending") or 0) >= 1

    # run-once indexes pending
    with patch("app.memory.faiss_memory._faiss_available", return_value=object()):
        run = siw.process_semantic_index_queue()
    assert run.get("status") == "ok"
    st1 = siw.get_semantic_worker_status()
    assert int(st1.get("pending") or 0) == 0
    assert int(st1.get("indexed") or 0) + int(st1.get("skipped") or 0) >= 1

    # cache avoids double embedding
    e1 = fm._ensure_entry_defaults(_entry("m_b", "Hybrid retrieval timeline semantic"))  # noqa: SLF001
    e2 = fm._ensure_entry_defaults(_entry("m_c", "Hybrid retrieval timeline semantic"))  # noqa: SLF001
    with patch("app.memory.faiss_memory._faiss_available", return_value=object()):
        r1 = fsm.add_memory_embedding(e1)
        r2 = fsm.add_memory_embedding(e2)
    assert r1.get("status") == "ok"
    assert r2.get("status") == "ok"
    cs = ec.embedding_cache_stats()
    assert int(cs.get("sets") or 0) >= 1
    assert int(cs.get("hits") or 0) >= 1

    # secret non indexed / non cached
    sec = fm._ensure_entry_defaults(_entry("m_secret", "Set api_key=sk-live-unsafe-now"))  # noqa: SLF001
    with patch("app.memory.faiss_memory._faiss_available", return_value=object()):
        rs = fsm.add_memory_embedding(sec)
    assert rs.get("status") == "ok"
    assert rs.get("added") is False
    assert str(rs.get("reason") or "") == "empty_or_sensitive"

    # /api/chat compatibility: must still respond with expected fields
    client = TestClient(app)
    gs = client.post("/guest/session")
    assert gs.status_code == 200
    sid = gs.json().get("session_id")
    with patch(
        "app.api.chat.generate_response",
        return_value={"output": "ok worker", "success": True, "provider": "mock", "status_code": 200},
    ):
        ch = client.post("/chat", json={"message": "Hello worker semantic queue"}, headers={"X-Guest-Session": sid})
    assert ch.status_code == 200
    body = ch.json()
    assert "output" in body and "memory_used" in body and "consolidation_recommended" in body

    # write_exchange adds queue job best-effort
    st_before = siw.get_semantic_worker_status()
    with patch("app.memory.faiss_memory._faiss_available", return_value=object()):
        wr = fm.write_exchange(
            source="test",
            user_message="Index this quickly",
            assistant_response="Done semantic queue",
            project="openchawn",
            user_key="user-worker",
            project_name_hint="openchawn",
            is_guest=False,
        )
    assert wr.saved is True
    st_after = siw.get_semantic_worker_status()
    assert int(st_after.get("pending") or 0) >= int(st_before.get("pending") or 0) + 1

    # status + endpoints shape
    ws = client.get("/memory/semantic/worker/status")
    assert ws.status_code == 200
    wb = ws.json()
    for k in ("pending", "indexed", "skipped", "errors"):
        assert k in wb
    ro = client.post("/memory/semantic/worker/run-once")
    assert ro.status_code == 200
    cst = client.get("/memory/semantic/cache/stats")
    assert cst.status_code == 200
    assert cst.json().get("status") == "ok"

    assert not _has_secret(ws.json())
    assert not _has_secret(ro.json())
    assert not _has_secret(cst.json())

    print("OK semantic_indexing_worker tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

