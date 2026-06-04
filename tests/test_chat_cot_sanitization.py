"""CoT safety: inline model reasoning must never be displayed or stored.

Wires app.utils.sanitizer.sanitize_response into the chat handler. The user
message is never sanitized; retrieval, providers and language mode are untouched.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import guest as guest_auth
from app.main import app
from app.memory.fractal_memory import MemoryWriteResult


def _reset_guest_state() -> None:
    guest_auth._sessions.clear()
    guest_auth._ip_sessions.clear()


def _fake_gen_factory(output: str):
    def _fake_gen(**_kwargs):
        return {
            "output": output,
            "success": True,
            "provider": "mock",
            "status_code": 200,
            "forced_french_runtime_removed": False,
            "prompt_contains_forced_french_before_sanitize": False,
        }

    return _fake_gen


def _guest_client(monkeypatch):
    monkeypatch.setenv("GUEST_DAILY_MESSAGE_LIMIT", "50")
    from app.settings import reload_settings

    reload_settings()
    _reset_guest_state()
    client = TestClient(app)
    created = client.post("/guest/session")
    assert created.status_code == 200
    sid = created.json()["session_id"]
    return client, {"X-Guest-Session": sid}


def test_inline_think_block_removed_from_api_response(monkeypatch):
    client, headers = _guest_client(monkeypatch)
    raw = "<think>secret internal plan</think>Hello"

    with patch("app.api.chat.generate_response", side_effect=_fake_gen_factory(raw)), patch(
        "app.api.chat.write_exchange",
        return_value=MemoryWriteResult(saved=False, reason="test_skip"),
    ):
        r = client.post("/chat", json={"message": "say hi in english"}, headers=headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output"] == "Hello"
    assert "<think>" not in body["output"]
    assert "secret" not in body["output"]


def test_stored_assistant_response_has_no_cot(monkeypatch):
    client, headers = _guest_client(monkeypatch)
    raw = "<think>do not store this reasoning</think>Final answer."

    captured: dict[str, str] = {}

    def _capture_write(**kwargs):
        captured["assistant_response"] = kwargs.get("assistant_response", "")
        captured["user_message"] = kwargs.get("user_message", "")
        return MemoryWriteResult(saved=True, reason="", entry_ids=("e1",))

    with patch("app.api.chat.generate_response", side_effect=_fake_gen_factory(raw)), patch(
        "app.api.chat.write_exchange", side_effect=_capture_write
    ):
        r = client.post("/chat", json={"message": "give me the answer"}, headers=headers)

    assert r.status_code == 200, r.text
    assert "assistant_response" in captured
    assert "<think>" not in captured["assistant_response"]
    assert "reasoning" not in captured["assistant_response"]
    assert captured["assistant_response"] == "Final answer."
    # user message must never be sanitized
    assert captured["user_message"] == "give me the answer"


def test_normal_response_without_reasoning_unchanged(monkeypatch):
    client, headers = _guest_client(monkeypatch)
    raw = "Just a normal answer with no reasoning tags."

    with patch("app.api.chat.generate_response", side_effect=_fake_gen_factory(raw)), patch(
        "app.api.chat.write_exchange",
        return_value=MemoryWriteResult(saved=False, reason="test_skip"),
    ):
        r = client.post("/chat", json={"message": "hello"}, headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["output"] == raw


def test_reasoning_only_response_returns_503(monkeypatch):
    """A response containing only CoT becomes empty after sanitization → 503, never served/stored."""
    client, headers = _guest_client(monkeypatch)
    raw = "<think>only hidden reasoning, no user-facing answer</think>"

    with patch("app.api.chat.generate_response", side_effect=_fake_gen_factory(raw)), patch(
        "app.api.chat.write_exchange",
        return_value=MemoryWriteResult(saved=False, reason="test_skip"),
    ) as mock_write:
        r = client.post("/chat", json={"message": "anything"}, headers=headers)

    assert r.status_code == 503
    mock_write.assert_not_called()
