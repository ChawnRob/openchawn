"""Web search injection into /chat assembly."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.chat import ChatRequest, assemble_chat_generation_inputs, handle_chat_request
from app.main import app
from app.settings import reload_settings
from app.tools.web_search import WebSearchResult


def _guest_user() -> dict:
    return {"is_guest": True, "guest_session_id": "guest-test-web-search", "ip": "127.0.0.1"}


def test_web_search_disabled_no_injection(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    reload_settings()

    req = ChatRequest(message="Recherche les dernières actualités IA")
    with patch("app.api.chat.web_search_sync") as mock_search:
        bundle = assemble_chat_generation_inputs(
            req, user=_guest_user(), persist_memory_side_effects=False
        )
    mock_search.assert_not_called()
    assert "WEB_SEARCH_RESULTS" not in bundle["user_message"]
    assert "Web search results are provided below" not in bundle["system_prompt"]


def test_web_search_enabled_injects_results(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    reload_settings()

    hits = [
        WebSearchResult(
            title="Fluxorca",
            url="https://fluxorca.com",
            snippet="Business platform for entrepreneurs.",
        )
    ]
    req = ChatRequest(message="Que fait fluxorca.com ?")
    with patch("app.api.chat.web_search_sync", return_value=hits) as mock_search:
        bundle = assemble_chat_generation_inputs(
            req, user=_guest_user(), persist_memory_side_effects=False
        )
    mock_search.assert_called_once()
    assert "WEB_SEARCH_RESULTS:" in bundle["user_message"]
    assert "https://fluxorca.com" in bundle["user_message"]
    assert "Web search results are provided below" in bundle["system_prompt"]
    assert bundle["web_search_used"] is True
    assert bundle["web_search_result_count"] == 1


def test_web_search_provider_failure_chat_still_works(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    reload_settings()

    req = ChatRequest(message="Va sur fluxorca.com")
    with patch("app.api.chat.web_search_sync", side_effect=RuntimeError("provider down")):
        bundle = assemble_chat_generation_inputs(
            req, user=_guest_user(), persist_memory_side_effects=False
        )
    assert bundle["web_search_used"] is True
    assert "WEB_SEARCH_RESULTS" in bundle["user_message"]
    assert "no usable results" in bundle["user_message"].lower()

    with patch("app.api.chat.web_search_sync", return_value=[]):
        with patch("app.api.chat.generate_response") as mock_llm:
            mock_llm.return_value = {
                "output": "Fluxorca is a business platform.",
                "provider_used": "groq",
                "model_used": "test",
                "fallback_used": False,
                "success": True,
                "status_code": 200,
                "error": None,
            }
            with patch("app.api.chat.write_exchange") as mock_write:
                mock_write.return_value = type("W", (), {"saved": False, "reason": "test"})()
                with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
                    out = handle_chat_request(req, _guest_user(), debug=False, http_mount_path="/chat")
    assert out["output"] == "Fluxorca is a business platform."
