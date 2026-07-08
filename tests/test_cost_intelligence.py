"""P1.5-COST — cost intelligence unit tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.core.cost_intelligence import (
    ChatCostTracker,
    CostEvent,
    anonymize_user_scope,
    is_cost_intelligence_enabled,
    record_chat_cost_safe,
    reset_cost_intelligence_for_tests,
)
from app.core.cost_pricing import (
    compute_llm_cost_usd,
    compute_web_search_cost_usd,
    estimate_tokens,
    merge_pricing_status,
    usd_to_eur,
)
from app.core.cost_store import persist_cost_event, query_cost_summary


@pytest.fixture(autouse=True)
def _reset_cost_store():
    reset_cost_intelligence_for_tests()
    yield
    reset_cost_intelligence_for_tests()


def test_anonymize_user_scope_roles():
    assert anonymize_user_scope({"is_guest": True}) == "guest"
    assert anonymize_user_scope({"is_owner": True}) == "owner"
    assert anonymize_user_scope({"user_role": "owner"}) == "owner"
    assert anonymize_user_scope({"user_id": 1}) == "user"


def test_estimate_tokens_and_llm_cost_known_provider():
    cost, inp, out, status = compute_llm_cost_usd(
        provider="groq",
        model="llama-3.1-8b-instant",
        input_tokens=1000,
        output_tokens=500,
    )
    assert inp == 1000
    assert out == 500
    assert cost > 0
    assert status == "complete"


def test_unknown_provider_partial_pricing():
    cost, _, _, status = compute_llm_cost_usd(
        provider="totally_unknown_provider",
        model="mystery-model",
        input_tokens=100,
        output_tokens=50,
    )
    assert cost == 0.0
    assert status in ("unknown", "partial")


def test_web_search_cost_tavily():
    cost, status = compute_web_search_cost_usd(provider="tavily", count=2)
    assert cost > 0
    assert status == "complete"


def test_total_cost_is_llm_plus_web():
    tracker = ChatCostTracker(
        request_id="req-1",
        user_scope="guest",
        sampled=True,
        enabled=True,
    )
    tracker.record_llm(
        provider="groq",
        model="llama-3.1-8b-instant",
        input_tokens=1000,
        output_tokens=200,
    )
    tracker.record_web_search(count=1, provider="tavily")
    event = tracker.finish()
    assert event is not None
    assert event.total_cost_usd == round(event.llm_cost_usd + event.web_search_cost_usd, 8)


def test_cost_event_store_has_no_user_content():
    event = {
        "request_id": "abc123",
        "user_scope": "guest",
        "provider": "groq",
        "model": "llama-3.1-8b-instant",
        "input_tokens": 10,
        "output_tokens": 5,
        "llm_cost_usd": 0.001,
        "web_search_count": 0,
        "web_search_cost_usd": 0.0,
        "vision_used": False,
        "document_used": False,
        "duration_ms": 42,
        "total_cost_usd": 0.001,
    }
    backend = persist_cost_event(event)
    assert backend in ("postgres", "sqlite", "jsonl")
    blob = json.dumps(event).lower()
    assert "password" not in blob
    assert "@" not in blob
    assert "prompt" not in blob


def test_disabled_intelligence_skips_tracking(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COST_INTELLIGENCE_ENABLED", "false")
    tracker = ChatCostTracker.start({"is_guest": True}, message="hello")
    assert tracker is None
    assert is_cost_intelligence_enabled() is False


def test_tracking_failure_does_not_raise():
    tracker = ChatCostTracker(
        request_id="fail-req",
        user_scope="user",
        sampled=True,
        enabled=True,
    )
    with patch("app.core.cost_intelligence.persist_cost_event", side_effect=RuntimeError("db down")):
        result = record_chat_cost_safe(tracker)
    assert result is not None
    assert result.request_id == "fail-req"


def test_merge_pricing_status_partial_wins_over_complete():
    assert merge_pricing_status("complete", "partial") == "partial"
    assert merge_pricing_status("complete", "unknown") == "unknown"


def test_usd_to_eur_conversion(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COST_USD_TO_EUR_RATE", "0.5")
    assert usd_to_eur(2.0) == 1.0


def test_summary_aggregates_persisted_events():
    for i in range(3):
        persist_cost_event(
            {
                "request_id": f"req-{i}",
                "user_scope": "guest",
                "provider": "groq",
                "model": "llama-3.1-8b-instant",
                "input_tokens": 100,
                "output_tokens": 50,
                "llm_cost_usd": 0.001,
                "web_search_count": 0,
                "web_search_cost_usd": 0.0,
                "vision_used": False,
                "document_used": False,
                "duration_ms": 100,
                "total_cost_usd": 0.001,
            }
        )
    summary = query_cost_summary(period="today")
    assert summary["total_requests"] == 3
    assert summary["total_cost_usd"] > 0
    assert "groq" in summary["by_provider"]
