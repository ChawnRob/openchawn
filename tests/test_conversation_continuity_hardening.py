"""P1.4.1 — conversation continuity hardening (store, scoring, group resolver)."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.api.chat import ChatRequest, assemble_chat_generation_inputs, handle_chat_request
from app.core.conversation_continuity import (
    TrackedEntity,
    clear_conversation_states,
    commit_conversation_continuity_turn,
    preview_conversation_continuity,
    resolve_conversation_continuity,
)
from app.core.conversation_continuity_store import (
    load_conversation_state,
    persist_conversation_state,
)


def _guest_user(session_id: str = "guest-hardening") -> dict:
    return {"is_guest": True, "guest_session_id": session_id, "ip": "127.0.0.1"}


@pytest.fixture(autouse=True)
def _reset_store():
    clear_conversation_states()
    yield
    clear_conversation_states()


def test_company_then_possessive_ai_reference():
    session = "guest:company-ai"
    resolve_conversation_continuity(
        session,
        "We reviewed the public strategy of Arcadia Systems.",
        language="en",
    )
    res = preview_conversation_continuity(session, "What is its AI stack?", language="en")
    assert res.has_reference is True
    assert res.resolved_entity is not None
    assert "Arcadia" in res.resolved_entity.text


def test_ab_comparison_which_is_cheaper():
    session = "guest:ab-compare"
    resolve_conversation_continuity(
        session,
        "Compare Nimbus Pack and Orbit Pack for pricing.",
        language="en",
    )
    res = preview_conversation_continuity(session, "Which one is cheaper?", language="en")
    assert res.comparison_mode is True
    assert len(res.resolved_entities) >= 2
    assert res.confidence in ("medium", "high")


def test_abc_ordinal_second():
    session = "guest:abc-second"
    resolve_conversation_continuity(
        session,
        "Options: Vertex One, Vertex Two and Vertex Three.",
        language="en",
    )
    res = preview_conversation_continuity(session, "Where is the second based?", language="en")
    assert res.resolved_entity is not None
    assert "Vertex Two" in res.resolved_entity.text


def test_ambiguity_clarification_without_llm():
    req = ChatRequest(message="What does it integrate with?")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch("app.api.chat.generate_response") as mock_llm:
            out = handle_chat_request(req, _guest_user("ambiguous-hardening"), debug=False, http_mount_path="/chat")
    mock_llm.assert_not_called()
    assert out.get("continuity_clarification") is True


def test_session_change_no_state_leak():
    resolve_conversation_continuity("guest:session-a", "Topic Alpha Corp is expanding.", language="en")
    res = preview_conversation_continuity("guest:session-b", "What does it sell?", language="en")
    assert res.confidence == "low"
    assert res.clarification


def test_expired_ttl_requires_clarification(monkeypatch: pytest.MonkeyPatch):
    session = "guest:ttl-expired"
    monkeypatch.setenv("CONVERSATION_CONTINUITY_TTL_SECONDS", "60")
    persist_conversation_state(
        session,
        {
            "conversation_id": session,
            "entities": [
                TrackedEntity(
                    text="Delta Works",
                    category="company",
                    turn_index=1,
                    mention_order=1,
                    last_seen_at=time.time() - 120,
                ).to_dict()
            ],
            "active_topic": "Delta Works",
            "active_category": "company",
            "turn_count": 1,
            "comparison_group": [],
            "updated_at": time.time() - 120,
        },
    )
    res = preview_conversation_continuity(session, "What is its product?", language="en")
    assert res.confidence == "low"
    assert res.clarification


def test_single_resolve_per_turn_in_assembly():
    session = "guest:single-resolve"
    user = _guest_user("single-resolve")
    resolve_conversation_continuity(session, "Quasar Labs published a new API.", language="en")
    continuity = preview_conversation_continuity(session, "What does it do?", language="en")
    req = ChatRequest(message="What does it do?")
    with patch("app.api.chat.preview_conversation_continuity") as mock_preview:
        with patch("app.api.chat.build_layered_memory_context", return_value=("", [])):
            assemble_chat_generation_inputs(
                req,
                user=user,
                persist_memory_side_effects=False,
                continuity=continuity,
            )
    mock_preview.assert_not_called()


def test_commit_only_after_explicit_call():
    session = "guest:commit-explicit"
    preview_conversation_continuity(session, "Helios Group announced a release.", language="en")
    assert load_conversation_state(session) is None
    commit_conversation_continuity_turn(session, "Helios Group announced a release.")
    stored = load_conversation_state(session)
    assert stored is not None
    assert int(stored.get("turn_count") or 0) == 1


def test_entity_scoring_prefers_recent_mentions():
    session = "guest:scoring"
    resolve_conversation_continuity(session, "Alpha Node and Beta Node are vendors.", language="en")
    resolve_conversation_continuity(session, "Beta Node released a new feature.", language="en")
    res = preview_conversation_continuity(session, "What does it offer?", language="en")
    assert res.resolved_entity is not None
    assert "Beta" in res.resolved_entity.text


def test_group_both_resolves_pair():
    session = "guest:group-both"
    resolve_conversation_continuity(session, "Kite Works and Dune Works are shortlisted.", language="en")
    res = preview_conversation_continuity(session, "Tell me about both.", language="en")
    assert len(res.resolved_entities) == 2
    assert res.comparison_mode is True
