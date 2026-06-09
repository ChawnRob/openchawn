"""
Durable last_image_context storage (structured summary only — no image bytes).

Postgres when MEMORY_DB_URL / DATABASE_URL is set (Railway multi-replica),
else SQLite via app.auth.database, else in-process RAM fallback.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("openchawn.files_intake.image_context")

_ram_fallback: dict[str, dict[str, Any]] = {}
_sqlite_ready = False
_postgres_ready = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_url() -> str:
    try:
        from app.memory.fractal_memory import resolve_memory_db_url

        return (resolve_memory_db_url() or "").strip()
    except Exception:
        return ""


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
            CREATE TABLE IF NOT EXISTS last_image_context (
                context_key TEXT PRIMARY KEY,
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
    CREATE TABLE IF NOT EXISTS last_image_context (
        context_key TEXT PRIMARY KEY,
        payload_json JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """
    with _postgres_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    _postgres_ready = True


def persist_image_context(context_key: str, payload: dict[str, Any]) -> str:
    """Write context; returns backend label used (postgres|sqlite|ram)."""
    key = (context_key or "").strip()
    if not key:
        return "ram"
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
                        INSERT INTO last_image_context (context_key, payload_json, updated_at)
                        VALUES (%s, %s::jsonb, %s)
                        ON CONFLICT (context_key) DO UPDATE SET
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
                "image_context postgres write failed | key=%s | error=%s",
                key[:32],
                exc.__class__.__name__,
            )

    try:
        _ensure_sqlite_schema()
        from app.auth.database import _get_connection

        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO last_image_context (context_key, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(context_key) DO UPDATE SET
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
            "image_context sqlite write failed | key=%s | error=%s",
            key[:32],
            exc.__class__.__name__,
        )

    _ram_fallback[key] = dict(payload)
    return "ram"


def load_image_context(context_key: str) -> dict[str, Any] | None:
    key = (context_key or "").strip()
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
                        "SELECT payload_json FROM last_image_context WHERE context_key = %s",
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
                "image_context postgres read failed | key=%s | error=%s",
                key[:32],
                exc.__class__.__name__,
            )

    try:
        _ensure_sqlite_schema()
        from app.auth.database import _get_connection

        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT payload_json FROM last_image_context WHERE context_key = ?",
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
            "image_context sqlite read failed | key=%s | error=%s",
            key[:32],
            exc.__class__.__name__,
        )

    return _ram_fallback.get(key)


def clear_image_context_persistence() -> None:
    global _sqlite_ready, _postgres_ready
    _ram_fallback.clear()

    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        try:
            _ensure_postgres_schema()
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM last_image_context")
                conn.commit()
        except Exception:
            pass

    try:
        _ensure_sqlite_schema()
        from app.auth.database import _get_connection

        conn = _get_connection()
        try:
            conn.execute("DELETE FROM last_image_context")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

    _sqlite_ready = False
    _postgres_ready = False


def clear_image_context_memory_cache() -> None:
    _ram_fallback.clear()
