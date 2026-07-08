"""P1.4.2 — conversation continuity reliability hardening."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.api.chat import ChatRequest, handle_chat_request
from app.core.conversation_continuity import (
    clear_conversation_states,
    continuity_debug_metadata,
    preview_conversation_continuity,
    resolve_conversation_continuity,
)
from app.core.conversation_continuity_store import (
    get_continuity_runtime_status,
    persist_conversation_state,
)
from app.main import app


def _guest_user(session_id: str = "guest-reliability") -> dict:
    return {"is_guest": True, "guest_session_id": session_id, "ip": "127.0.0.1"}


@pytest.fixture(autouse=True)
def _reset_store():
    clear_conversation_states()
    yield
    clear_conversation_states()


def test_jensen_elon_il_forces_clarification():
    session = "guest:jensen-elon"
    resolve_conversation_continuity(session, "Jensen Huang dirige Nvidia.", language="fr")
    resolve_conversation_continuity(session, "Elon Musk dirige Tesla.", language="fr")
    res = preview_conversation_continuity(session, "Que commercialise-t-il ?", language="fr")
    assert res.confidence == "low"
    assert res.clarification
    assert res.continuity_reason == "person_pronoun_ambiguity"
    assert res.resolved_entity is None

    req = ChatRequest(message="Que commercialise-t-il ?")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch("app.api.chat.generate_response") as mock_llm:
            out = handle_chat_request(req, _guest_user("jensen-elon"), debug=False, http_mount_path="/chat")
    mock_llm.assert_not_called()
    assert out.get("continuity_clarification") is True


def test_two_companies_it_does_not_over_trigger():
    session = "guest:two-companies-it"
    resolve_conversation_continuity(
        session,
        "We reviewed the public strategy of Arcadia Systems.",
        language="en",
    )
    resolve_conversation_continuity(
        session,
        "Mercedes-Benz also published an AI roadmap.",
        language="en",
    )
    res = preview_conversation_continuity(session, "What is its AI stack?", language="en")
    assert res.confidence in ("medium", "high")
    assert res.resolved_entity is not None
    assert res.continuity_reason != "person_pronoun_ambiguity"


def test_two_companies_elle_does_not_over_trigger():
    session = "guest:two-companies-elle"
    resolve_conversation_continuity(
        session,
        "L'entreprise Lumen Grid opère en Europe.",
        language="fr",
    )
    resolve_conversation_continuity(
        session,
        "L'entreprise Arcadia Systems a publié une feuille de route IA.",
        language="fr",
    )
    res = preview_conversation_continuity(session, "Quelle est son IA ?", language="fr")
    assert res.confidence in ("medium", "high")
    assert res.resolved_entity is not None
    assert res.continuity_reason != "person_pronoun_ambiguity"


def test_explicit_person_name_disambiguates():
    session = "guest:explicit-elon"
    resolve_conversation_continuity(session, "Jensen Huang dirige Nvidia.", language="fr")
    resolve_conversation_continuity(session, "Elon Musk dirige Tesla.", language="fr")
    res = preview_conversation_continuity(session, "Que commercialise Elon Musk ?", language="fr")
    assert res.continuity_reason != "person_pronoun_ambiguity"
    assert not (res.confidence == "low" and res.continuity_reason == "person_pronoun_ambiguity")

    req = ChatRequest(message="Que commercialise Elon Musk ?")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch("app.api.chat.generate_response", return_value={"output": "Tesla commercialise des véhicules.", "success": True}) as mock_llm:
            with patch("app.api.chat.write_exchange") as mock_write:
                mock_write.return_value.saved = False
                mock_write.return_value.reason = "test"
                mock_write.return_value.entry_ids = []
                out = handle_chat_request(req, _guest_user("explicit-elon"), debug=False, http_mount_path="/chat")
    mock_llm.assert_called_once()
    assert out.get("continuity_clarification") is not True


def test_ab_comparison_still_resolves():
    session = "guest:ab-reliability"
    resolve_conversation_continuity(
        session,
        "Compare Nimbus Pack and Orbit Pack for pricing.",
        language="en",
    )
    res = preview_conversation_continuity(session, "Which one is cheaper?", language="en")
    assert res.comparison_mode is True
    assert len(res.resolved_entities) >= 2
    assert res.confidence in ("medium", "high")


def test_ordinal_second_still_resolves():
    session = "guest:ordinal-reliability"
    resolve_conversation_continuity(
        session,
        "Options: Vertex One, Vertex Two and Vertex Three.",
        language="en",
    )
    res = preview_conversation_continuity(session, "Où est basée la deuxième ?", language="fr")
    assert res.resolved_entity is not None
    assert "Vertex Two" in res.resolved_entity.text


def test_blank_user_scope_still_clarifies():
    session = "guest:blank-scope"
    res = preview_conversation_continuity(session, "What does it integrate with?", language="en")
    assert res.confidence == "low"
    assert res.clarification

    req = ChatRequest(message="What does it integrate with?")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch("app.api.chat.generate_response") as mock_llm:
            out = handle_chat_request(req, _guest_user("blank-scope"), debug=False, http_mount_path="/chat")
    mock_llm.assert_not_called()
    assert out.get("continuity_clarification") is True


def test_debug_true_on_clarification_short_circuit():
    session = "guest:debug-clarify"
    resolve_conversation_continuity(session, "Jensen Huang dirige Nvidia.", language="fr")
    resolve_conversation_continuity(session, "Elon Musk dirige Tesla.", language="fr")
    req = ChatRequest(message="Que commercialise-t-il ?")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch("app.api.chat.generate_response") as mock_llm:
            out = handle_chat_request(
                req, _guest_user("debug-clarify"), debug=True, http_mount_path="/chat"
            )
    mock_llm.assert_not_called()
    assert out.get("continuity_clarification") is True
    assert out["continuity_confidence"] == "low"
    assert out["continuity_reason"] == "person_pronoun_ambiguity"
    assert "continuity_candidates" in out
    assert "resolved_referent" in out


def test_debug_true_returns_continuity_metadata():
    session = "guest:debug-meta"
    resolve_conversation_continuity(session, "Orion Systems released a new API.", language="en")
    req = ChatRequest(message="What does it do?")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch("app.api.chat.generate_response", return_value={"output": "It provides APIs.", "success": True}):
            with patch("app.api.chat.write_exchange") as mock_write:
                mock_write.return_value.saved = False
                mock_write.return_value.reason = "test"
                mock_write.return_value.entry_ids = []
                out = handle_chat_request(req, _guest_user("debug-meta"), debug=True, http_mount_path="/chat")
    assert "continuity_confidence" in out
    assert "continuity_clarification" in out
    assert "continuity_candidates" in out
    assert "resolved_referent" in out
    assert "continuity_reason" in out
    assert isinstance(out["continuity_candidates"], list)
    assert all(isinstance(c, str) for c in out["continuity_candidates"])


def test_debug_metadata_helper_is_non_sensitive():
    session = "guest:debug-helper"
    resolve_conversation_continuity(session, "Jensen Huang dirige Nvidia.", language="fr")
    resolve_conversation_continuity(session, "Elon Musk dirige Tesla.", language="fr")
    res = preview_conversation_continuity(session, "Que commercialise-t-il ?", language="fr")
    meta = continuity_debug_metadata(res)
    blob = json.dumps(meta).lower()
    assert "jensen" not in blob
    assert "elon" not in blob
    assert "nvidia" not in blob
    assert "tesla" not in blob
    assert meta["continuity_confidence"] == "low"
    assert meta["continuity_clarification"] is True
    assert meta["continuity_reason"] == "person_pronoun_ambiguity"


def test_continuity_status_exposes_no_user_content():
    session = "guest:status-safe"
    persist_conversation_state(
        session,
        {
            "conversation_id": session,
            "entities": [],
            "active_topic": "Secret Topic Corp",
            "active_category": "company",
            "turn_count": 1,
            "comparison_group": [],
            "updated_at": 1.0,
        },
    )
    status = get_continuity_runtime_status()
    blob = json.dumps(status).lower()
    assert status["enabled"] is True
    assert status["backend"] in ("postgres", "sqlite", "ram", "unknown")
    assert isinstance(status["ttl_seconds"], int)
    assert "secret" not in blob
    assert "topic corp" not in blob

    client = TestClient(app)
    resp = client.get("/api/continuity/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert "backend" in body
    assert "secret" not in json.dumps(body).lower()


def test_production_railway_blocks_silent_ram_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CONVERSATION_CONTINUITY_ALLOW_DEV_FALLBACK", raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("OPENCHAWN_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "")

    from app.core import conversation_continuity_store as store

    store._ram_fallback.clear()
    backend = store.persist_conversation_state(
        "guest:railway-guard",
        {"conversation_id": "guest:railway-guard", "entities": [], "turn_count": 0},
    )
    assert backend == "none"
    assert "guest:railway-guard" not in store._ram_fallback


def test_single_person_she_still_resolves():
    session = "guest:single-person"
    resolve_conversation_continuity(session, "Tell me about Morgan Blake's product roadmap.", language="en")
    res = preview_conversation_continuity(session, "What does she sell?", language="en")
    assert res.resolved_entity is not None
    assert "Morgan" in res.resolved_entity.text
    assert res.continuity_reason != "person_pronoun_ambiguity"
