"""P1.5-COST — cost API and /chat integration tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.chat import ChatRequest, handle_chat_request
from app.core.cost_intelligence import get_cost_debug_snapshot, reset_cost_intelligence_for_tests
from app.core.cost_store import query_cost_summary
from app.main import app


def _guest_user(session_id: str = "guest-cost") -> dict:
    return {"is_guest": True, "guest_session_id": session_id, "ip": "127.0.0.1"}


@pytest.fixture(autouse=True)
def _reset_cost(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COST_INTELLIGENCE_ENABLED", "true")
    monkeypatch.setenv("COST_SAMPLE_RATE", "1.0")
    reset_cost_intelligence_for_tests()
    yield
    reset_cost_intelligence_for_tests()


def test_chat_records_cost_event_when_enabled():
    req = ChatRequest(message="What is OpenChawn?")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch(
            "app.api.chat.generate_response",
            return_value={
                "output": "OpenChawn is a conversational platform.",
                "success": True,
                "provider_used": "groq",
                "model_used": "llama-3.1-8b-instant",
            },
        ):
            with patch("app.api.chat.write_exchange") as mock_write:
                mock_write.return_value.saved = False
                mock_write.return_value.reason = "test"
                mock_write.return_value.entry_ids = []
                handle_chat_request(req, _guest_user("cost-record"), debug=False, http_mount_path="/chat")
    summary = query_cost_summary(period="today")
    assert summary["total_requests"] >= 1


def test_chat_survives_cost_tracking_failure():
    req = ChatRequest(message="Hello")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch(
            "app.api.chat.generate_response",
            return_value={"output": "Hi", "success": True, "provider_used": "groq", "model_used": "llama"},
        ):
            with patch("app.api.chat.write_exchange") as mock_write:
                mock_write.return_value.saved = False
                mock_write.return_value.reason = "test"
                mock_write.return_value.entry_ids = []
                with patch("app.core.cost_intelligence.persist_cost_event", side_effect=RuntimeError("boom")):
                    out = handle_chat_request(req, _guest_user("cost-fail"), debug=False, http_mount_path="/chat")
    assert out.get("output") == "Hi"


def test_debug_true_exposes_cost_without_prompt(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COST_DEFAULT_CURRENCY", "EUR")
    req = ChatRequest(message="Secret prompt about Jensen Huang at Nvidia")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch(
            "app.api.chat.generate_response",
            return_value={
                "output": "A neutral platform overview.",
                "success": True,
                "provider_used": "groq",
                "model_used": "llama-3.1-8b-instant",
            },
        ):
            with patch("app.api.chat.write_exchange") as mock_write:
                mock_write.return_value.saved = False
                mock_write.return_value.reason = "test"
                mock_write.return_value.entry_ids = []
                out = handle_chat_request(req, _guest_user("cost-debug"), debug=True, http_mount_path="/chat")
    cost_blob = json.dumps(
        {
            "cost_estimate": out.get("cost_estimate"),
            "cost_currency": out.get("cost_currency"),
            "cost_pricing_status": out.get("cost_pricing_status"),
        }
    ).lower()
    assert "cost_estimate" in out
    assert "cost_currency" in out
    assert "cost_pricing_status" in out
    assert "jensen" not in cost_blob
    assert "nvidia" not in cost_blob
    assert "prompt" not in cost_blob


def test_cost_status_no_sensitive_leak():
    client = TestClient(app)
    resp = client.get("/api/cost/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "enabled" in body
    assert "storage_backend" in body
    blob = json.dumps(body).lower()
    assert "@" not in blob
    assert "password" not in blob
    assert "prompt" not in blob


def test_cost_summary_endpoint():
    client = TestClient(app)
    resp = client.get("/api/cost/summary?period=today")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_requests" in body
    assert "total_cost_usd" in body
    assert "by_provider" in body


def test_cost_debug_endpoint_operational_only():
    client = TestClient(app)
    resp = client.get("/api/cost/debug")
    assert resp.status_code == 200
    body = resp.json()
    assert "pricing_status" in body
    blob = json.dumps(body).lower()
    assert "conversation" not in blob
    assert "email" not in blob


def test_disabled_tracking_no_events(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COST_INTELLIGENCE_ENABLED", "false")
    req = ChatRequest(message="No tracking")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch(
            "app.api.chat.generate_response",
            return_value={"output": "OK", "success": True, "provider_used": "groq", "model_used": "llama"},
        ):
            with patch("app.api.chat.write_exchange") as mock_write:
                mock_write.return_value.saved = False
                mock_write.return_value.reason = "test"
                mock_write.return_value.entry_ids = []
                handle_chat_request(req, _guest_user("cost-off"), debug=False, http_mount_path="/chat")
    summary = query_cost_summary(period="today")
    assert summary["total_requests"] == 0
    snap = get_cost_debug_snapshot()
    assert snap["last_provider"] is None

def test_unknown_model_pricing_status_partial():
    req = ChatRequest(message="Hi")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch(
            "app.api.chat.generate_response",
            return_value={
                "output": "Hello",
                "success": True,
                "provider_used": "unknown_provider_xyz",
                "model_used": "unknown-model-abc",
            },
        ):
            with patch("app.api.chat.write_exchange") as mock_write:
                mock_write.return_value.saved = False
                mock_write.return_value.reason = "test"
                mock_write.return_value.entry_ids = []
                out = handle_chat_request(req, _guest_user("cost-partial"), debug=True, http_mount_path="/chat")
    assert out.get("cost_pricing_status") in ("partial", "unknown")
