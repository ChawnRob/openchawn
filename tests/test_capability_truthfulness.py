"""P1.3 — capability truthfulness when web search is enabled but not used."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.api.chat import ChatRequest, assemble_chat_generation_inputs
from app.settings import reload_settings
from app.tools.web_search import (
    WEB_CAPABILITY_TRUTHFULNESS_INSTRUCTION,
    WEB_PROTECTED_REQUEST_INSTRUCTION,
    build_web_capability_system_addon,
)


def _guest_user() -> dict:
    return {"is_guest": True, "guest_session_id": "guest-cap-truth", "ip": "127.0.0.1"}


def test_build_web_capability_addon_variants():
    assert "WEB_CAPABILITY_TRUTHFULNESS" in build_web_capability_system_addon(protected_request=False)
    assert "WEB_PROTECTED_REQUEST" in build_web_capability_system_addon(protected_request=True)


def test_capability_instruction_contains_required_french_phrase():
    phrase = (
        "Je peux rechercher des informations publiques via OpenChawn quand la demande déclenche l'outil web"
    )
    assert phrase in WEB_CAPABILITY_TRUTHFULNESS_INSTRUCTION
    assert phrase in WEB_PROTECTED_REQUEST_INSTRUCTION


def test_web_enabled_no_search_injects_capability_truthfulness(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    reload_settings()

    req = ChatRequest(message="Bonjour comment ça va ?")
    with patch("app.api.chat.web_search_sync") as mock_search:
        bundle = assemble_chat_generation_inputs(
            req, user=_guest_user(), persist_memory_side_effects=False
        )
    mock_search.assert_not_called()
    assert bundle["web_search_used"] is False
    assert "WEB_CAPABILITY_TRUTHFULNESS" in bundle["system_prompt"]
    assert "WEB_SEARCH_RESULTS" not in bundle["user_message"]
    assert "NEVER claim you lack a web search tool" in bundle["system_prompt"]


def test_protected_request_injects_refusal_without_web_search(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    reload_settings()

    req = ChatRequest(message="Connecte-toi à mon LinkedIn")
    with patch("app.api.chat.web_search_sync") as mock_search:
        bundle = assemble_chat_generation_inputs(
            req, user=_guest_user(), persist_memory_side_effects=False
        )
    mock_search.assert_not_called()
    assert bundle["protected_web_request"] is True
    assert bundle["web_search_used"] is False
    assert "WEB_PROTECTED_REQUEST" in bundle["system_prompt"]
    assert "comptes privés" in bundle["system_prompt"]


def test_web_disabled_no_capability_addon(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    reload_settings()

    req = ChatRequest(message="Bonjour")
    bundle = assemble_chat_generation_inputs(
        req, user=_guest_user(), persist_memory_side_effects=False
    )
    assert "WEB_CAPABILITY_TRUTHFULNESS" not in bundle["system_prompt"]
    assert "WEB_PROTECTED_REQUEST" not in bundle["system_prompt"]


def test_discovery_intent_still_uses_web_search_not_capability_addon(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    reload_settings()

    req = ChatRequest(message="Recherche Robert Lumet LinkedIn")
    with patch("app.api.chat.web_search_sync", return_value=[]):
        bundle = assemble_chat_generation_inputs(
            req, user=_guest_user(), persist_memory_side_effects=False
        )
    assert bundle["web_search_used"] is True
    assert "WEB_SEARCH_RESULTS" in bundle["user_message"]
    assert "WEB_CAPABILITY_TRUTHFULNESS" not in bundle["system_prompt"]
    assert "Web search results are provided below" in bundle["system_prompt"]
