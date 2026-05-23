"""Memory/database runtime audit — safe status and isolated read/write probe."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_memory_runtime_status_defaults():
    from app.core.memory_runtime_status import get_memory_runtime_status

    st = get_memory_runtime_status(verify_read_write=False)
    assert "database_configured" in st
    assert st["database_provider"] in ("sqlite", "postgres")
    assert st["fractal_memory_backend"] in ("json", "postgres")
    assert st["short_memory_enabled"] is True
    assert st["long_memory_enabled"] is True
    assert isinstance(st["vector_memory_enabled"], bool)
    assert st["memory_read_write_verified"] is False


def test_memory_runtime_status_read_write_verified():
    from app.core.memory_runtime_status import get_memory_runtime_status

    st = get_memory_runtime_status(verify_read_write=True)
    assert st["memory_read_write_verified"] is True


def test_api_memory_runtime_status_endpoint():
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/memory/runtime-status")
    assert r.status_code == 200
    data = r.json()
    assert "database_configured" in data
    assert "memory_read_write_verified" in data
    assert data["memory_read_write_verified"] is False
    assert "password" not in str(data).lower()
    assert "secret" not in str(data).lower()


def test_no_supabase_or_short_long_env_required():
    import os

    from app.settings import get_settings

    s = get_settings()
    # Documented fractal/auth vars — not SUPABASE_* or SHORT_MEMORY_*
    assert hasattr(s, "memory_backend")
    assert hasattr(s, "database_path") or hasattr(s, "database_url")
    for key in ("SUPABASE_URL", "SHORT_MEMORY_ENABLED", "LONG_MEMORY_ENABLED", "VECTOR_DB_URL"):
        assert key not in os.environ or not os.environ.get(key)
