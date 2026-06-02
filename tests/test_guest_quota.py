"""Guest quota defaults and 429 behavior."""

from __future__ import annotations

from app.auth import guest as guest_auth


def test_staging_guest_daily_limit_default(monkeypatch):
    monkeypatch.delenv("GUEST_DAILY_MESSAGE_LIMIT", raising=False)
    monkeypatch.delenv("OPENCHAWN_GUEST_DAILY_LIMIT", raising=False)
    monkeypatch.setenv("OPENCHAWN_ENV", "staging")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    from app.settings import reload_settings

    assert reload_settings().guest_daily_limit == 50


def test_production_guest_daily_limit_default(monkeypatch):
    monkeypatch.delenv("GUEST_DAILY_MESSAGE_LIMIT", raising=False)
    monkeypatch.delenv("OPENCHAWN_GUEST_DAILY_LIMIT", raising=False)
    monkeypatch.setenv("OPENCHAWN_ENV", "production")

    from app.settings import reload_settings

    assert reload_settings().guest_daily_limit == 20


def test_guest_quota_blocks_after_limit(monkeypatch):
    monkeypatch.setenv("GUEST_DAILY_MESSAGE_LIMIT", "1")
    from app.settings import reload_settings

    reload_settings()
    guest_auth._sessions.clear()
    guest_auth._ip_sessions.clear()

    ip = "127.0.0.1"
    session = guest_auth.create_guest_session(ip=ip)
    sid = session["session_id"]

    allowed = guest_auth.check_guest_quota(session_id=sid, ip=ip)
    blocked = guest_auth.check_guest_quota(session_id=sid, ip=ip)

    assert allowed["allowed"] is True
    assert allowed["remaining"] == 0
    assert blocked["allowed"] is False
    assert blocked["remaining"] == 0
