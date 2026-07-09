"""
Durable cost event storage (P1.5-COST).

Postgres when DATABASE_URL / MEMORY_DB_URL is set,
SQLite in dev/test, JSONL fallback in dev/test only.
No silent RAM persistence in production/Railway.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("openchawn.cost.store")

_jsonl_ready = False
_sqlite_ready = False
_postgres_ready = False
_last_backend = "unknown"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


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
    raw = (os.getenv("COST_ALLOW_DEV_FALLBACK") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _allow_jsonl_sqlite_fallback() -> bool:
    if _explicit_dev_fallback_allowed():
        return True
    if _is_production_env() or _is_railway_deploy():
        return False
    return _is_dev_or_test()


def _resolve_db_url() -> str:
    try:
        from app.memory.fractal_memory import resolve_memory_db_url

        return (resolve_memory_db_url() or "").strip()
    except Exception:
        return (os.getenv("DATABASE_URL") or os.getenv("MEMORY_DB_URL") or "").strip()


def _is_postgres_url(url: str) -> bool:
    low = (url or "").strip().lower()
    return low.startswith("postgres://") or low.startswith("postgresql://")


def _jsonl_path() -> str:
    raw = (os.getenv("COST_EVENTS_JSONL_PATH") or "").strip()
    if raw:
        return raw
    return os.path.join(os.getcwd(), "data", "cost_events.jsonl")


def _ensure_sqlite_schema() -> None:
    global _sqlite_ready
    if _sqlite_ready:
        return
    from app.auth.database import _get_connection

    conn = _get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cost_events (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                user_scope TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                llm_cost_usd REAL NOT NULL DEFAULT 0,
                web_search_count INTEGER NOT NULL DEFAULT 0,
                web_search_cost_usd REAL NOT NULL DEFAULT 0,
                vision_used INTEGER NOT NULL DEFAULT 0,
                document_used INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                total_cost_usd REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cost_events_created_at ON cost_events(created_at)"
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
    CREATE TABLE IF NOT EXISTS cost_events (
        id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL,
        user_scope TEXT NOT NULL,
        provider TEXT,
        model TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        llm_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
        web_search_count INTEGER NOT NULL DEFAULT 0,
        web_search_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
        vision_used BOOLEAN NOT NULL DEFAULT FALSE,
        document_used BOOLEAN NOT NULL DEFAULT FALSE,
        duration_ms INTEGER NOT NULL DEFAULT 0,
        total_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """
    idx = "CREATE INDEX IF NOT EXISTS idx_cost_events_created_at ON cost_events(created_at)"
    with _postgres_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(idx)
        conn.commit()
    _postgres_ready = True


def _row_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id") or str(uuid.uuid4()),
        "request_id": str(event.get("request_id") or ""),
        "user_scope": str(event.get("user_scope") or "user"),
        "provider": event.get("provider"),
        "model": event.get("model"),
        "input_tokens": event.get("input_tokens"),
        "output_tokens": event.get("output_tokens"),
        "llm_cost_usd": float(event.get("llm_cost_usd") or 0.0),
        "web_search_count": int(event.get("web_search_count") or 0),
        "web_search_cost_usd": float(event.get("web_search_cost_usd") or 0.0),
        "vision_used": bool(event.get("vision_used")),
        "document_used": bool(event.get("document_used")),
        "duration_ms": int(event.get("duration_ms") or 0),
        "total_cost_usd": float(event.get("total_cost_usd") or 0.0),
        "created_at": event.get("created_at") or _now_iso(),
    }


def persist_cost_event(event: dict[str, Any]) -> str:
    """Persist one cost event; returns backend label."""
    global _last_backend
    row = _row_from_event(event)
    if not row["request_id"]:
        _last_backend = "none"
        return "none"

    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        try:
            _ensure_postgres_schema()
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO cost_events (
                            id, request_id, user_scope, provider, model,
                            input_tokens, output_tokens, llm_cost_usd,
                            web_search_count, web_search_cost_usd,
                            vision_used, document_used, duration_ms, total_cost_usd, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            row["id"],
                            row["request_id"],
                            row["user_scope"],
                            row["provider"],
                            row["model"],
                            row["input_tokens"],
                            row["output_tokens"],
                            row["llm_cost_usd"],
                            row["web_search_count"],
                            row["web_search_cost_usd"],
                            row["vision_used"],
                            row["document_used"],
                            row["duration_ms"],
                            row["total_cost_usd"],
                            row["created_at"],
                        ),
                    )
                conn.commit()
            _last_backend = "postgres"
            return "postgres"
        except Exception as exc:
            logger.warning(
                "cost postgres write failed | error=%s",
                exc.__class__.__name__,
            )

    if _allow_jsonl_sqlite_fallback():
        try:
            _ensure_sqlite_schema()
            from app.auth.database import _get_connection

            conn = _get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO cost_events (
                        id, request_id, user_scope, provider, model,
                        input_tokens, output_tokens, llm_cost_usd,
                        web_search_count, web_search_cost_usd,
                        vision_used, document_used, duration_ms, total_cost_usd, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["request_id"],
                        row["user_scope"],
                        row["provider"],
                        row["model"],
                        row["input_tokens"],
                        row["output_tokens"],
                        row["llm_cost_usd"],
                        row["web_search_count"],
                        row["web_search_cost_usd"],
                        1 if row["vision_used"] else 0,
                        1 if row["document_used"] else 0,
                        row["duration_ms"],
                        row["total_cost_usd"],
                        row["created_at"],
                    ),
                )
                conn.commit()
                _last_backend = "sqlite"
                return "sqlite"
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                "cost sqlite write failed | error=%s",
                exc.__class__.__name__,
            )

        try:
            path = _jsonl_path()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            _last_backend = "jsonl"
            return "jsonl"
        except Exception as exc:
            logger.warning(
                "cost jsonl write failed | error=%s",
                exc.__class__.__name__,
            )

    if _is_production_env() or _is_railway_deploy():
        logger.error(
            "cost event not persisted: production/Railway requires Postgres "
            "(set DATABASE_URL or COST_ALLOW_DEV_FALLBACK=true for explicit opt-in)"
        )
    else:
        logger.warning("cost event not persisted (no durable backend)")
    _last_backend = "unknown"
    return "none"


def _period_start(period: str) -> datetime:
    now = _now_utc()
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_requests = len(rows)
    if total_requests == 0:
        return {
            "total_requests": 0,
            "total_cost_usd": 0.0,
            "total_cost_eur": 0.0,
            "average_cost_per_request": 0.0,
            "average_duration_ms": 0,
            "by_provider": {},
            "by_model": {},
            "web_search_cost": 0.0,
            "llm_cost": 0.0,
            "vision_request_count": 0,
            "document_request_count": 0,
        }

    total_cost = sum(float(r.get("total_cost_usd") or 0) for r in rows)
    llm_cost = sum(float(r.get("llm_cost_usd") or 0) for r in rows)
    web_cost = sum(float(r.get("web_search_cost_usd") or 0) for r in rows)
    avg_duration = int(sum(int(r.get("duration_ms") or 0) for r in rows) / total_requests)
    by_provider: dict[str, dict[str, float | int]] = {}
    by_model: dict[str, dict[str, float | int]] = {}

    for r in rows:
        prov = str(r.get("provider") or "unknown")
        mdl = str(r.get("model") or "unknown")
        cost = float(r.get("total_cost_usd") or 0)
        by_provider.setdefault(prov, {"requests": 0, "cost_usd": 0.0})
        by_provider[prov]["requests"] = int(by_provider[prov]["requests"]) + 1
        by_provider[prov]["cost_usd"] = round(float(by_provider[prov]["cost_usd"]) + cost, 8)
        by_model.setdefault(mdl, {"requests": 0, "cost_usd": 0.0})
        by_model[mdl]["requests"] = int(by_model[mdl]["requests"]) + 1
        by_model[mdl]["cost_usd"] = round(float(by_model[mdl]["cost_usd"]) + cost, 8)

    from app.core.cost_pricing import usd_to_eur

    return {
        "total_requests": total_requests,
        "total_cost_usd": round(total_cost, 8),
        "total_cost_eur": usd_to_eur(total_cost),
        "average_cost_per_request": round(total_cost / total_requests, 8),
        "average_duration_ms": avg_duration,
        "by_provider": by_provider,
        "by_model": by_model,
        "web_search_cost": round(web_cost, 8),
        "llm_cost": round(llm_cost, 8),
        "vision_request_count": sum(1 for r in rows if r.get("vision_used")),
        "document_request_count": sum(1 for r in rows if r.get("document_used")),
    }


def _fetch_events_since(since: datetime) -> list[dict[str, Any]]:
    since_iso = since.isoformat()
    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        try:
            _ensure_postgres_schema()
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT provider, model, input_tokens, output_tokens,
                               llm_cost_usd, web_search_count, web_search_cost_usd,
                               vision_used, document_used, duration_ms, total_cost_usd, created_at
                        FROM cost_events
                        WHERE created_at >= %s
                        ORDER BY created_at ASC
                        """,
                        (since,),
                    )
                    rows = cur.fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("cost postgres read failed | error=%s", exc.__class__.__name__)

    if _allow_jsonl_sqlite_fallback():
        try:
            _ensure_sqlite_schema()
            from app.auth.database import _get_connection

            conn = _get_connection()
            try:
                cur = conn.execute(
                    """
                    SELECT provider, model, input_tokens, output_tokens,
                           llm_cost_usd, web_search_count, web_search_cost_usd,
                           vision_used, document_used, duration_ms, total_cost_usd, created_at
                    FROM cost_events
                    WHERE created_at >= ?
                    ORDER BY created_at ASC
                    """,
                    (since_iso,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    r["vision_used"] = bool(r.get("vision_used"))
                    r["document_used"] = bool(r.get("document_used"))
                return rows
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("cost sqlite read failed | error=%s", exc.__class__.__name__)
    return []


def query_cost_summary(*, period: str = "today") -> dict[str, Any]:
    since = _period_start(period)
    rows = _fetch_events_since(since)
    summary = _aggregate_rows(rows)
    summary["period"] = period
    return summary


def query_cost_status() -> dict[str, Any]:
    today = _period_start("today")
    rows = _fetch_events_since(today)
    summary = _aggregate_rows(rows)
    last_at: str | None = None
    if rows:
        last_at = str(rows[-1].get("created_at") or "")

    backend = _last_backend
    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        backend = "postgres"
    elif backend == "unknown" and _allow_jsonl_sqlite_fallback():
        backend = "sqlite" if _sqlite_ready else "jsonl"

    return {
        "events_count": summary["total_requests"],
        "last_event_at": last_at,
        "daily_cost_estimate": summary["total_cost_usd"],
        "daily_request_count": summary["total_requests"],
        "storage_backend": backend,
    }


def count_all_events() -> int:
    return query_cost_status()["events_count"]


def clear_cost_events_store() -> None:
    """Test helper — wipe cost events."""
    global _sqlite_ready, _postgres_ready, _last_backend
    db_url = _resolve_db_url()
    if db_url and _is_postgres_url(db_url):
        try:
            _ensure_postgres_schema()
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM cost_events")
                conn.commit()
        except Exception:
            pass
    if _allow_jsonl_sqlite_fallback():
        try:
            _ensure_sqlite_schema()
            from app.auth.database import _get_connection

            conn = _get_connection()
            try:
                conn.execute("DELETE FROM cost_events")
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
        path = _jsonl_path()
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    _sqlite_ready = False
    _postgres_ready = False
    _last_backend = "unknown"
