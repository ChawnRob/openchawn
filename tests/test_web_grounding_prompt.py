"""Web search grounding — system prompt and injection contract."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.api.chat import ChatRequest, assemble_chat_generation_inputs
from app.settings import reload_settings
from app.tools.web_search import (
    WEB_SEARCH_GROUNDING_INSTRUCTION,
    build_web_search_system_addon,
    format_web_search_results_block,
)
from app.tools.web_search import WebSearchResult


def _guest_user() -> dict:
    return {"is_guest": True, "guest_session_id": "guest-grounding", "ip": "127.0.0.1"}


_GROUNDING_SECTIONS = (
    "## Faits observés",
    "## Inférences",
    "## Hypothèses non confirmées",
    "## Sources utilisées",
)


def test_web_search_results_inject_grounding_sections_in_system_prompt(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "tavily")
    reload_settings()

    hits = [
        WebSearchResult(
            title="Fluxorca",
            url="https://fluxorca.com",
            snippet="Plateforme business pour entrepreneurs.",
            source_index=1,
        )
    ]
    req = ChatRequest(message="Va sur fluxorca.com et résume ce que tu trouves")
    with patch("app.api.chat.web_search_sync", return_value=hits):
        bundle = assemble_chat_generation_inputs(
            req, user=_guest_user(), persist_memory_side_effects=False
        )

    sp = bundle["system_prompt"]
    for section in _GROUNDING_SECTIONS:
        assert section in sp
    assert "WEB_SEARCH_GROUNDING_RULES" in sp
    assert "Non trouvé dans les sources fournies" in sp
    assert "source_index: 1" in bundle["user_message"]


def test_competitor_analysis_must_be_marked_inference_in_grounding_rules():
    addon = build_web_search_system_addon(has_results=True)
    assert "Zapier" in addon or "competitors" in addon.lower()
    assert "## Inférences" in addon
    assert "MUST be labeled as inferences" in addon or "labeled as inferences" in addon


def test_empty_sources_use_insufficient_results_instruction(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "tavily")
    reload_settings()

    req = ChatRequest(message="Que fait fluxorca.com ?")
    with patch("app.api.chat.web_search_sync", return_value=[]):
        bundle = assemble_chat_generation_inputs(
            req, user=_guest_user(), persist_memory_side_effects=False
        )

    sp = bundle["system_prompt"]
    assert "did not return enough elements" in sp.lower()
    assert WEB_SEARCH_GROUNDING_INSTRUCTION not in sp
    assert "no usable results" in bundle["user_message"].lower()


def test_format_block_includes_source_index_fields():
    hits = [
        WebSearchResult(
            title="Example",
            url="https://example.org",
            snippet="Short snippet.",
            source_index=1,
        ),
        WebSearchResult(
            title="Other",
            url="https://other.example",
            snippet="Another snippet.",
            source_index=2,
        ),
    ]
    block = format_web_search_results_block(hits)
    assert "source_index: 1" in block
    assert "source_index: 2" in block
    assert "title: Example" in block
    assert "url: https://example.org" in block
