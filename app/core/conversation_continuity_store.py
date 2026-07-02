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
_last_backend = "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_dev_or_test() -> bool:
    if "pytest" in sys.modules:
        return True
    env = (os.getenv("OPENCHAWN_ENV") or "").strip().lower()
    return env in ("", "development", "dev", "test", "local")


def _is_production_env() -> bool:
    for var in ("OPENCHAWN_ENV", "APP_ENV", "RAILWAY_ENVIRONMENT"):
        val = (os.getenv(var) or "").strip().lower()
        if val in ("production", "prod"):
            return True
    return False


def _is_railway_deploy() -> bool:
    return bool((os.getenv("RAILWAY_ENVIRONMENT") or "").strip())


def _explicit_dev_fallback_allowed() -> bool:
    raw = (os.getenv("CONVERSATION_CONTINUITY_ALLOW_DEV_FALLBACK") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _allow_ram_sqlite_fallback() -> bool:
    if _explicit_dev_fallback_allowed():
        return True
    if _is_production_env() or _is_railway_deploy():
        return False
    return _is_dev_or_test()


def _runtime_environment_label() -> str:
    for var in ("OPENCHAWN_ENV", "APP_ENV", "RAILWAY_ENVIRONMENT"):
        val = (os.getenv(var) or "").strip()
        if val:
            return val
    return "unknown"


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
    global _last_backend
    key = (conversation_id or "").strip()
    if not key:
        _last_backend = "none"
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
            _last_backend = "postgres"
            return "postgres"
        except Exception as exc:
            logger.warning(
                "continuity postgres write failed | id=%s | error=%s",
                key[:32],
                exc.__class__.__name__,
            )

    if _allow_ram_sqlite_fallback():
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
                _last_backend = "sqlite"
                return "sqlite"
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                "continuity sqlite write failed | id=%s | error=%s",
                key[:32],
                exc.__class__.__name__,
            )
        logger.warning(
            "continuity using in-process RAM fallback | id=%s | env=%s",
            key[:32],
            _runtime_environment_label(),
        )
        _ram_fallback[key] = dict(payload)
        _last_backend = "ram"
        return "ram"

    if _is_production_env() or _is_railway_deploy():
        logger.error(
            "continuity state not persisted: production/Railway requires Postgres "
            "(set DATABASE_URL or CONVERSATION_CONTINUITY_ALLOW_DEV_FALLBACK=true for explicit opt-in) | id=%s",
            key[:32],
        )
    else:
        logger.warning("continuity state not persisted (no durable backend) | id=%s", key[:32])
    _last_backend = "unknown"
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

    if _allow_ram_sqlite_fallback():
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

    if _allow_ram_sqlite_fallback():
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


def _resolve_active_backend() -> str:
    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        return "postgres"
    if _last_backend in ("postgres", "sqlite", "ram"):
        return _last_backend
    if _allow_ram_sqlite_fallback():
        return "sqlite" if _sqlite_ready else "ram"
    return "unknown"


def _safe_active_conversation_count() -> int | None:
    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        try:
            _ensure_postgres_schema()
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) AS c FROM conversation_continuity_state")
                    row = cur.fetchone()
            if row and row.get("c") is not None:
                return int(row["c"])
        except Exception:
            return None
    if _allow_ram_sqlite_fallback():
        try:
            _ensure_sqlite_schema()
            from app.auth.database import _get_connection

            conn = _get_connection()
            try:
                row = conn.execute("SELECT COUNT(*) AS c FROM conversation_continuity_state").fetchone()
            finally:
                conn.close()
            if row:
                return int(row["c"])
        except Exception:
            return len(_ram_fallback) if _ram_fallback else 0
        return len(_ram_fallback)
    return None


def get_continuity_runtime_status() -> dict[str, Any]:
    """Operational continuity status — no user content or entity names."""
    from app.core.conversation_continuity import _state_ttl_seconds

    return {
        "enabled": True,
        "backend": _resolve_active_backend(),
        "ttl_seconds": _state_ttl_seconds(),
        "environment": _runtime_environment_label(),
        "active_conversation_count": _safe_active_conversation_count(),
    }
