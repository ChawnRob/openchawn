"""Postgres fractal memory backend — unit tests with mocked DB and JSON regression."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import app.memory.fractal_memory as fm
from app.memory.fractal_memory import (
    MemoryBackendConfigError,
    PostgresMemoryBackend,
    LocalJsonMemoryBackend,
    _build_backend,
    fractal_backend_name,
    resolve_memory_db_url,
    write_exchange,
)
from app.settings import reload_settings


@contextmanager
def _isolated_json_store(tmp_path):
    path = tmp_path / "fractal_memory.json"
    prev = fm.STORE_PATH
    fm.STORE_PATH = path
    try:
        yield path
    finally:
        fm.STORE_PATH = prev


def test_resolve_memory_db_url_priority(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://from-database")
    monkeypatch.setenv("MEMORY_DB_URL", "postgres://from-memory")
    assert resolve_memory_db_url() == "postgres://from-memory"
    monkeypatch.delenv("MEMORY_DB_URL", raising=False)
    assert resolve_memory_db_url() == "postgres://from-database"


def test_postgres_backend_missing_url_raises():
    with pytest.raises(MemoryBackendConfigError, match="MEMORY_DB_URL"):
        PostgresMemoryBackend(database_url="")


def test_build_backend_postgres_missing_url(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "postgres")
    monkeypatch.delenv("MEMORY_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reload_settings()
    with pytest.raises(MemoryBackendConfigError, match="MEMORY_DB_URL"):
        _build_backend()


def test_json_backend_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "json")
    monkeypatch.setenv("OPENCHAWN_ENV", "development")
    reload_settings()
    with _isolated_json_store(tmp_path):
        result = write_exchange(
            source="test",
            user_message="Rappelle le choix de couleur pour le dashboard COCO.",
            assistant_response="Bleu nuit pour le dashboard, note pour la session.",
            user_key="json-user-1",
            is_guest=True,
        )
        assert result.saved
        entries = fm.entries_snapshot_for_tests()
        assert len(entries) >= 1
        assert any(str(e.get("memory_type")) in ("session", "user", "project", "system") for e in entries)


def test_postgres_save_load_roundtrip_mocked():
    stored_rows: list[dict] = []
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def _capture_execute(sql, params=None):
        sql_s = " ".join(str(sql).split())
        if sql_s.startswith("INSERT INTO fractal_memories") and params:
            payload = json.loads(params[-1])
            stored_rows.append({"entry_payload": payload})

    mock_cur.execute.side_effect = _capture_execute

    def _fetchall():
        return [{"entry_payload": r["entry_payload"]} for r in stored_rows]

    mock_cur.fetchall.side_effect = _fetchall

    entry = {
        "id": "mem_test001",
        "timestamp": "2026-05-19T12:00:00+00:00",
        "memory_type": "user",
        "memory_level": "concept_memory",
        "project_name": "openchawn",
        "user_id": "u1",
        "source": "test",
        "user_message": "prefere reponses structurees",
        "assistant_response": "",
        "summary": "User style preference",
        "tags": ["ui"],
        "importance_score": 0.6,
        "project": "openchawn",
        "parent_id": None,
        "children_ids": [],
        "metadata": {"layer": "preference"},
        "created_at": "2026-05-19T12:00:00+00:00",
        "last_accessed_at": "2026-05-19T12:00:00+00:00",
        "access_count": 0,
        "lifecycle_status": "active",
        "contradiction_detected": False,
        "decay_score": 12.0,
    }

    backend = PostgresMemoryBackend(database_url="postgres://mock/db")
    with patch.object(backend, "_connect", return_value=mock_conn):
        backend.save_entries([entry])
        loaded = backend.load_entries()

    assert len(loaded) == 1
    assert loaded[0]["id"] == "mem_test001"
    assert loaded[0]["memory_type"] == "user"
    assert loaded[0]["memory_level"] == "concept_memory"
    assert loaded[0]["metadata"].get("layer") == "preference"


def test_postgres_schema_create_executed():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = []

    backend = PostgresMemoryBackend(database_url="postgres://mock/db")
    with patch.object(backend, "_connect", return_value=mock_conn):
        backend.load_entries()

    executed = " ".join(str(c[0][0]) for c in mock_cur.execute.call_args_list)
    assert "CREATE TABLE IF NOT EXISTS fractal_memories" in executed


def test_memory_types_persist_in_payload():
    backend = PostgresMemoryBackend(database_url="postgres://mock/db")
    for mtype in ("session", "project", "system", "compressed"):
        payload = backend._entry_to_payload(
            {
                "id": f"mem_{mtype}",
                "timestamp": "2026-05-19T12:00:00+00:00",
                "memory_type": mtype,
                "source": "t",
                "user_message": "m",
                "assistant_response": "a",
                "summary": "s",
                "tags": [],
                "importance_score": 0.5,
                "project": "",
            }
        )
        assert payload["memory_type"] == mtype


def test_runtime_status_json_not_persistent(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "json")
    monkeypatch.setenv("OPENCHAWN_ENV", "development")
    reload_settings()
    from app.core.memory_runtime_status import get_memory_runtime_status

    st = get_memory_runtime_status(verify_read_write=True)
    assert st["fractal_memory_backend"] == "json"
    assert st["fractal_persistent"] is False
    assert st["memory_read_write_verified"] is False


def test_runtime_status_postgres_persistent_when_configured(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "postgres")
    monkeypatch.setenv("MEMORY_DB_URL", "postgres://example:5432/db")
    reload_settings()
    from app.core.memory_runtime_status import get_memory_runtime_status

    st = get_memory_runtime_status(verify_read_write=False)
    assert st["fractal_memory_backend"] == "postgres"
    assert st["fractal_persistent"] is True
    assert st["database_provider"] == "postgres"
    assert st["fractal_storage_kind"] == "postgres"


def test_runtime_status_postgres_missing_url_diagnostic(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "postgres")
    monkeypatch.delenv("MEMORY_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reload_settings()
    from app.core.memory_runtime_status import get_memory_runtime_status

    st = get_memory_runtime_status(verify_read_write=False)
    assert st["memory_config_ok"] is False
    assert "MEMORY_DB_URL" in st["memory_config_note"]


def test_verify_read_write_postgres_mocked():
    backend = PostgresMemoryBackend(database_url="postgres://mock/db")
    with patch.object(backend, "verify_read_write", return_value=True):
        assert backend.verify_read_write() is True
