"""
Durable conversation continuity state (short-term entities/topics per conversation_id).

Postgres JSONB when DATABASE_URL / MEMORY_DB_URL is set (Railway multi-replica),
SQLite in dev/test, in-process RAM fallback only in dev/test.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("openchawn.conversation_continuity.store")

_ram_fallback: dict[str, dict[str, Any]] = {}
_sqlite_ready = False
_postgres_ready = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_dev_or_test() -> bool:
    if "pytest" in sys.modules:
        return True
    env = (os.getenv("OPENCHAWN_ENV") or "").strip().lower()
    return env in ("", "development", "dev", "test", "local")


def _resolve_db_url() -> str:
    try:
        from app.memory.fractal_memory import resolve_memory_db_url

        return (resolve_memory_db_url() or "").strip()
    except Exception:
        return (os.getenv("DATABASE_URL") or os.getenv("MEMORY_DB_URL") or "").strip()


def _is_postgres_url(url: str) -> bool:
    low = (url or "").strip().lower()
    return low.startswith("postgres://") or low.startswith("postgresql://")


def _ensure_sqlite_schema() -> None:
    global _sqlite_ready
    if _sqlite_ready:
        return
    from app.auth.database import _get_connection

    conn = _get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_continuity_state (
                conversation_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        _sqlite_ready = True
    finally:
        conn.close()


def _postgres_connect():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_resolve_db_url(), row_factory=dict_row)


def _ensure_postgres_schema() -> None:
    global _postgres_ready
    if _postgres_ready:
        return
    sql = """
    CREATE TABLE IF NOT EXISTS conversation_continuity_state (
        conversation_id TEXT PRIMARY KEY,
        payload_json JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """
    with _postgres_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    _postgres_ready = True


def persist_conversation_state(conversation_id: str, payload: dict[str, Any]) -> str:
    """Write state; returns backend label (postgres|sqlite|ram|none)."""
    key = (conversation_id or "").strip()
    if not key:
        return "none"
    payload = dict(payload)
    if "updated_at" not in payload:
        payload["updated_at"] = time.time()
    body = json.dumps(payload, ensure_ascii=False)
    updated_at = _now_iso()

    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        try:
            _ensure_postgres_schema()
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO conversation_continuity_state (conversation_id, payload_json, updated_at)
                        VALUES (%s, %s::jsonb, %s)
                        ON CONFLICT (conversation_id) DO UPDATE SET
                            payload_json = EXCLUDED.payload_json,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (key, body, updated_at),
                    )
                conn.commit()
            _ram_fallback[key] = dict(payload)
            return "postgres"
        except Exception as exc:
            logger.warning(
                "continuity postgres write failed | id=%s | error=%s",
                key[:32],
                exc.__class__.__name__,
            )

    if _is_dev_or_test():
        try:
            _ensure_sqlite_schema()
            from app.auth.database import _get_connection

            conn = _get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO conversation_continuity_state (conversation_id, payload_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(conversation_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (key, body, updated_at),
                )
                conn.commit()
                _ram_fallback[key] = dict(payload)
                return "sqlite"
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                "continuity sqlite write failed | id=%s | error=%s",
                key[:32],
                exc.__class__.__name__,
            )
        _ram_fallback[key] = dict(payload)
        return "ram"

    logger.warning("continuity state not persisted (production without postgres) | id=%s", key[:32])
    return "none"


def load_conversation_state(conversation_id: str) -> dict[str, Any] | None:
    key = (conversation_id or "").strip()
    if not key:
        return None

    cached = _ram_fallback.get(key)
    if cached:
        return dict(cached)

    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        try:
            _ensure_postgres_schema()
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT payload_json FROM conversation_continuity_state WHERE conversation_id = %s",
                        (key,),
                    )
                    row = cur.fetchone()
            if row and row.get("payload_json"):
                payload = row["payload_json"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if isinstance(payload, dict):
                    _ram_fallback[key] = dict(payload)
                    return dict(payload)
        except Exception as exc:
            logger.warning(
                "continuity postgres read failed | id=%s | error=%s",
                key[:32],
                exc.__class__.__name__,
            )

    if _is_dev_or_test():
        try:
            _ensure_sqlite_schema()
            from app.auth.database import _get_connection

            conn = _get_connection()
            try:
                row = conn.execute(
                    "SELECT payload_json FROM conversation_continuity_state WHERE conversation_id = ?",
                    (key,),
                ).fetchone()
            finally:
                conn.close()
            if row:
                payload = json.loads(row["payload_json"])
                if isinstance(payload, dict):
                    _ram_fallback[key] = dict(payload)
                    return dict(payload)
        except Exception as exc:
            logger.warning(
                "continuity sqlite read failed | id=%s | error=%s",
                key[:32],
                exc.__class__.__name__,
            )
        return _ram_fallback.get(key)

    return None


def clear_conversation_state_store() -> None:
    global _sqlite_ready, _postgres_ready
    _ram_fallback.clear()

    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        try:
            _ensure_postgres_schema()
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM conversation_continuity_state")
                conn.commit()
        except Exception:
            pass

    if _is_dev_or_test():
        try:
            _ensure_sqlite_schema()
            from app.auth.database import _get_connection

            conn = _get_connection()
            try:
                conn.execute("DELETE FROM conversation_continuity_state")
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    _sqlite_ready = False
    _postgres_ready = False


def clear_conversation_state_memory_cache() -> None:
    _ram_fallback.clear()
