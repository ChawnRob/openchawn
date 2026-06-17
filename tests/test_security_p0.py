"""P0 security — memory auth, user isolation, prod secret, log privacy, seed_admin."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth.database import create_user, init_db
from app.auth.security import create_token, hash_password
from app.settings import reload_settings

ROOT = Path(__file__).resolve().parents[1]
SEED_ADMIN = ROOT / "seed_admin.py"


def _auth_headers(user_id: int, email: str) -> dict[str, str]:
    token = create_token(user_id, email)
    return {"Authorization": f"Bearer {token}"}


def _create_test_user(email: str, password: str = "test-password-123") -> dict:
    init_db()
    user = create_user(email, hash_password(password), "Test User", "default")
    assert user is not None
    return user


@pytest.fixture(autouse=True)
def _reset_settings_after_prod_secret_tests(monkeypatch):
    yield
    monkeypatch.setenv("OPENCHAWN_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-change-me-in-production")
    reload_settings()


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/memory/recent"),
        ("POST", "/memory/search"),
        ("GET", "/memory/importance/top"),
        ("GET", "/memory"),
    ],
)
def test_memory_routes_require_auth(client, method, path):
    if method == "POST":
        r = client.post(path, json={"query": "test"})
    else:
        r = client.get(path)
    assert r.status_code == 401


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def test_user_cannot_read_other_users_memory(client):
    user_a = _create_test_user(_unique_email("user-a-security"))
    user_b = _create_test_user(_unique_email("user-b-security"))
    headers_a = _auth_headers(user_a["id"], user_a["email"])

    fake_entries = [
        {
            "id": "mem_a",
            "user_id": f"user-{user_a['id']}",
            "summary": "secret A",
            "importance_score": 0.9,
            "long_term_value": 0.5,
            "timestamp": "2026-01-01T00:00:00Z",
            "memory_type": "session",
            "recurrence_score": 0.1,
            "semantic_density": 0.1,
            "contradiction_risk": 0.0,
        },
        {
            "id": "mem_b",
            "user_id": f"user-{user_b['id']}",
            "summary": "secret B",
            "importance_score": 0.95,
            "long_term_value": 0.6,
            "timestamp": "2026-01-02T00:00:00Z",
            "memory_type": "session",
            "recurrence_score": 0.2,
            "semantic_density": 0.2,
            "contradiction_risk": 0.0,
        },
    ]

    with patch("app.memory.fractal_memory.entries_snapshot_for_tests", return_value=fake_entries):
        r = client.get("/memory/importance/top", headers=headers_a)
    assert r.status_code == 200
    items = r.json().get("items") or []
    ids = {str(x.get("id")) for x in items}
    assert "mem_a" in ids
    assert "mem_b" not in ids


def test_prod_rejects_default_dev_secret(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("OPENCHAWN_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-change-me-in-production")
    with pytest.raises(RuntimeError, match="OPENCHAWN_ENV=production"):
        reload_settings()


def test_prod_rejects_empty_secret(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("OPENCHAWN_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="OPENCHAWN_ENV=production"):
        reload_settings()


def test_dev_allows_default_secret(monkeypatch):
    monkeypatch.setenv("OPENCHAWN_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-change-me-in-production")
    settings = reload_settings()
    assert settings.secret_key == "dev-secret-change-me-in-production"


def test_register_login_logs_do_not_contain_plain_email(client, caplog):
    email = _unique_email("privacy-log-test")
    password = "privacy-password-123"
    caplog.set_level(logging.INFO, logger="openchawn")

    with caplog.at_level(logging.INFO, logger="openchawn"):
        r = client.post(
            "/register",
            json={
                "email": email,
                "password": password,
                "display_name": "Privacy",
            },
        )
    assert r.status_code == 200

    with caplog.at_level(logging.INFO, logger="openchawn"):
        r2 = client.post("/login", json={"email": email, "password": password})
    assert r2.status_code == 200

    for record in caplog.records:
        if record.name != "openchawn":
            continue
        msg = record.getMessage()
        if "Nouveau user" in msg or "Login:" in msg:
            assert email not in msg
            assert "email_hash=" in msg


def test_seed_admin_has_no_hardcoded_credentials():
    text = SEED_ADMIN.read_text(encoding="utf-8")
    assert "@" not in re.findall(r'=\s*["\'][^"\']+["\']', text)
    assert "password" not in text.lower() or "OPENCHAWN_SEED_PASSWORD" in text
    assert "OPENCHAWN_SEED_EMAIL" in text
    assert "OPENCHAWN_SEED_PASSWORD" in text
