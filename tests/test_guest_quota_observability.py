"""Guest quota observability counters and diagnostics endpoint."""

from __future__ import annotations

import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import guest as guest_auth
from app.core.guest_quota_observability import (
    get_guest_quota_observability_overview,
    reset_guest_quota_observability_for_tests,
)
from app.main import app


def _reset_guest_state() -> None:
    guest_auth._sessions.clear()
    guest_auth._ip_sessions.clear()
    reset_guest_quota_observability_for_tests()


def test_quota_block_increments_counters(monkeypatch):
    monkeypatch.setenv("GUEST_DAILY_MESSAGE_LIMIT", "1")
    from app.settings import reload_settings

    reload_settings()
    _reset_guest_state()

    ip = "10.0.0.8"
    session = guest_auth.create_guest_session(ip=ip)
    sid = session["session_id"]

    guest_auth.check_guest_quota(session_id=sid, ip=ip)
    blocked = guest_auth.check_guest_quota(session_id=sid, ip=ip)

    assert blocked["allowed"] is False
    assert blocked.get("block_reason") == "daily_limit_exceeded"

    overview = get_guest_quota_observability_overview()
    counters = overview["counters"]
    assert counters.get("quota_message_ok", 0) >= 1
    assert counters.get("block_reason:daily_limit_exceeded", 0) >= 1
    assert overview["summary"]["quota_checks_blocked"] >= 1


def test_unknown_session_block_reason(monkeypatch):
    monkeypatch.setenv("GUEST_DAILY_MESSAGE_LIMIT", "5")
    from app.settings import reload_settings

    reload_settings()
    _reset_guest_state()

    result = guest_auth.check_guest_quota(session_id="guest_missing", ip="10.0.0.9")
    assert result["allowed"] is False
    assert result.get("block_reason") == "unknown_session"

    overview = get_guest_quota_observability_overview()
    assert overview["counters"].get("block_reason:unknown_session", 0) >= 1


def test_observability_endpoint_returns_safe_shape():
    _reset_guest_state()
    client = TestClient(app)
    r = client.get("/guest/quota/observability?recent=5")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "counters" in body
    assert "live_store" in body
    assert "recent_events" in body
    assert "observability_version" in body
    for ev in body["recent_events"]:
        assert "ip_fingerprint" in ev
        assert "session_prefix" in ev or ev.get("event") == "chat_rate_limit_blocked"


def test_chat_quota_429_includes_block_reason_header(monkeypatch):
    monkeypatch.setenv("GUEST_DAILY_MESSAGE_LIMIT", "1")
    from app.settings import reload_settings

    reload_settings()
    _reset_guest_state()

    def _fake_gen(**_kwargs):
        return {
            "output": "mock",
            "success": True,
            "provider": "mock",
            "status_code": 200,
        }

    client = TestClient(app)
    created = client.post("/guest/session")
    assert created.status_code == 200
    sid = created.json()["session_id"]
    headers = {"X-Guest-Session": sid}

    from app.memory.fractal_memory import MemoryWriteResult

    with patch("app.api.chat.generate_response", side_effect=_fake_gen), patch(
        "app.api.chat.write_exchange",
        return_value=MemoryWriteResult(saved=False, reason="test_skip"),
    ):
        time.sleep(2.1)
        first = client.post("/chat", json={"message": "hello once"}, headers=headers)
        assert first.status_code == 200
        time.sleep(2.1)
        second = client.post("/chat", json={"message": "hello twice"}, headers=headers)

    assert second.status_code == 429
    assert second.headers.get("x-guest-quota-block-reason") == "daily_limit_exceeded"
