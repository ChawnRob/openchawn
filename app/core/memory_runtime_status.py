"""Safe memory/database runtime audit — non-secret fields only."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from app.config import DATABASE_PATH
from app.settings import get_settings


def _auth_database_configured() -> bool:
    raw = (DATABASE_PATH or os.environ.get("OPENCHAWN_DB_PATH") or "").strip()
    if not raw:
        return False
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path.parent.exists() or path.exists()


def _auth_database_provider() -> str:
    url = (get_settings().database_url or "").strip()
    if url.startswith("postgres"):
        return "postgres"
    return "sqlite"


def _fractal_backend_name() -> str:
    return (get_settings().memory_backend or "json").strip().lower() or "json"


def _faiss_available() -> bool:
    try:
        from app.memory import faiss_memory as fsm

        return bool(fsm._faiss_available())  # type: ignore[attr-defined]
    except Exception:
        return False


def _verify_fractal_read_write() -> bool:
    """Isolated JSON round-trip; does not touch production store."""
    try:
        import app.memory.fractal_memory as fm

        with tempfile.TemporaryDirectory(prefix="oc_mem_rw_") as td:
            path = Path(td) / "fractal_memory.json"
            prev = fm.STORE_PATH
            fm.STORE_PATH = path
            try:
                w = fm.write_exchange(
                    source="memory_runtime_audit",
                    user_message="Le projet openchawn utilise DeepSeek sur Railway.",
                    assistant_response="Confirmation enregistree pour les tests memoire.",
                    user_key="audit-probe-user",
                    is_guest=True,
                )
                if not w.saved:
                    return False
                ctx, mems = fm.build_layered_memory_context(
                    "DeepSeek Railway",
                    user_key="audit-probe-user",
                    is_guest=True,
                    persist_memory_side_effects=False,
                )
                return bool(mems) and len((ctx or "").strip()) > 0
            finally:
                fm.STORE_PATH = prev
    except Exception:
        return False
    return False


def get_memory_runtime_status(*, verify_read_write: bool = False) -> dict[str, Any]:
    """
    Aggregate safe runtime status for operators.
    Never includes credentials, connection strings, or API keys.
    """
    s = get_settings()
    fractal = _fractal_backend_name()
    fractal_persistent = fractal == "postgres" and bool((s.memory_db_url or "").strip())

    short_enabled = True  # session layer in fractal MEMORY_TYPES
    long_enabled = True  # system / project / user / compressed layers

    vector_enabled = _faiss_available()

    rw_verified = _verify_fractal_read_write() if verify_read_write else False

    storage_hint = "json_file"
    if fractal == "postgres":
        storage_hint = "postgres_prepared"
    elif fractal == "json":
        storage_hint = "json_file"

    return {
        "database_configured": _auth_database_configured(),
        "database_provider": _auth_database_provider(),
        "fractal_memory_backend": fractal,
        "fractal_storage_kind": storage_hint,
        "fractal_persistent": fractal_persistent,
        "short_memory_enabled": short_enabled,
        "long_memory_enabled": long_enabled,
        "vector_memory_enabled": vector_enabled,
        "memory_read_write_verified": rw_verified,
        "auth_db_note": "SQLite users/business registry (OPENCHAWN_DB_PATH), separate from fractal chat memory",
        "chat_memory_note": "Official chat path: fractal_memory build_layered_memory_context / write_exchange",
    }
