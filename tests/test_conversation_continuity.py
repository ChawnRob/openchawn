"""P1.4 — universal conversational continuity resolver (generic scenarios)."""

from __future__ import annotations

import pytest

from app.api.chat import ChatRequest, assemble_chat_generation_inputs, handle_chat_request
from app.core.conversation_continuity import (
    clear_conversation_states,
    extract_entities,
    resolve_conversation_continuity,
)
from app.files_intake.session_image_context import LastImageContext, set_last_image_context
from unittest.mock import patch


def _guest_user(session_id: str = "guest-continuity-test") -> dict:
    return {"is_guest": True, "guest_session_id": session_id, "ip": "127.0.0.1"}


@pytest.fixture(autouse=True)
def _reset_continuity_state():
    clear_conversation_states()
    yield
    clear_conversation_states()


@pytest.fixture(autouse=True)
def _reset_image_context():
    from app.files_intake.session_image_context import clear_image_context_store

    clear_image_context_store()
    yield
    clear_image_context_store()


def test_extract_entities_generic_no_hardcoded_brands():
    ents = extract_entities(
        "NovaCorp launched the Orion platform in Berlin. See https://example.org/spec.pdf",
        turn_index=1,
    )
    labels = {e.text for e in ents}
    categories = {e.category for e in ents}
    assert "NovaCorp" in labels or any("NovaCorp" in e.text for e in ents)
    assert len(ents) >= 2


def test_two_people_then_he_sells():
    session = "guest:two-people"
    resolve_conversation_continuity(
        session,
        "Atlas Labs sells analytics tools. Beacon Systems sells sensors.",
        language="en",
    )
    res = resolve_conversation_continuity(session, "What does he sell?", language="en")
    assert res.has_reference is True
    assert res.confidence in ("medium", "high")
    assert res.resolved_entity is not None
    assert res.resolved_entity.category == "person"
    assert "Beacon" in res.resolved_entity.text or "Atlas" in res.resolved_entity.text


def test_two_companies_then_second_based():
    session = "guest:two-companies"
    resolve_conversation_continuity(session, "Compare Helix Dynamics and Prism Analytics.", language="en")
    res = resolve_conversation_continuity(session, "Where is the second based?", language="en")
    assert res.has_reference is True
    assert res.resolved_entity is not None
    assert res.resolved_entity.text == "Prism Analytics"


def test_uploaded_image_then_analyse_detail():
    session = "guest:image-followup"
    set_last_image_context(
        session,
        LastImageContext(
            media_id="img_test_1",
            filename="diagram.png",
            mime_type="image/png",
            description="A flowchart with three labeled nodes.",
            detected_elements=["node A", "node B", "connector"],
            extracted_text="Step 1",
            created_at="2026-06-04T12:00:00+00:00",
        ),
    )
    resolve_conversation_continuity(session, "I uploaded a diagram for review.", language="en", image_label="diagram.png")
    res = resolve_conversation_continuity(
        session,
        "Analyze this detail in the image.",
        language="en",
        image_label="diagram.png",
    )
    assert res.has_reference is True
    assert res.resolved_entity is not None
    assert res.resolved_entity.category == "image"


def test_project_discussion_then_next_step():
    session = "guest:project-step"
    resolve_conversation_continuity(
        session,
        "We are planning the Horizon migration project with three milestones.",
        language="en",
    )
    res = resolve_conversation_continuity(session, "What is the next step?", language="en")
    assert res.has_reference is True
    assert res.confidence in ("medium", "high")
    assert res.active_topic


def test_document_then_summarize_it():
    session = "guest:document-it"
    resolve_conversation_continuity(
        session,
        "Please review the Q2 strategy report.pdf for the board.",
        language="en",
    )
    res = resolve_conversation_continuity(session, "Summarize it in five bullets.", language="en")
    assert res.has_reference is True
    assert res.resolved_entity is not None
    assert res.resolved_entity.category in ("document", "file")


def test_user_in_memory_topic_is_other_person_not_user():
    session = "guest:user-vs-topic"
    resolve_conversation_continuity(session, "Tell me about Morgan Blake's product roadmap.", language="en")
    res = resolve_conversation_continuity(session, "What does she sell?", language="en")
    assert res.resolved_entity is not None
    assert "Morgan" in res.resolved_entity.text
    assert res.resolved_entity.is_user_self is False


def test_low_confidence_returns_clarification_without_llm():
    session = "guest:ambiguous"
    res = resolve_conversation_continuity(session, "What does it integrate with?", language="en")
    assert res.confidence == "low"
    assert res.clarification

    req = ChatRequest(message="What does it integrate with?")
    with patch("app.api.chat.check_guest_quota", return_value={"allowed": True, "remaining": 10, "limit": 20}):
        with patch("app.api.chat.generate_response") as mock_llm:
            out = handle_chat_request(req, _guest_user("ambiguous"), debug=False, http_mount_path="/chat")
    mock_llm.assert_not_called()
    assert out.get("continuity_clarification") is True
    assert out["output"]


def test_continuity_block_injected_before_memory_in_assembly():
    session = "guest:assembly-order"
    user = _guest_user("assembly-order")
    resolve_conversation_continuity(session, "Orion Systems released a new API.", language="en")

    req = ChatRequest(message="What does it do?")
    with patch("app.api.chat.build_layered_memory_context", return_value=("SESSION MEMORY BLOCK", [])):
        bundle = assemble_chat_generation_inputs(req, user=user, persist_memory_side_effects=False)

    um = bundle["user_message"]
    continuity_pos = um.find("CONVERSATION CONTINUITY")
    memory_pos = um.find("SESSION MEMORY BLOCK")
    user_pos = um.find("── USER REQUEST ──")
    assert continuity_pos != -1
    assert memory_pos != -1
    assert continuity_pos < memory_pos < user_pos
    assert bundle["continuity_has_reference"] is True


def test_french_demonstrative_company_reference():
    session = "guest:fr-company"
    resolve_conversation_continuity(session, "L'entreprise Lumen Grid opère en Europe.", language="fr")
    res = resolve_conversation_continuity(session, "Cette entreprise est basée où ?", language="fr")
    assert res.resolved_entity is not None
    assert "Lumen" in res.resolved_entity.text


def test_state_ttl_and_max_entities_constants():
    from app.core import conversation_continuity as cc

    assert cc.MAX_RECENT_ENTITIES == 12
    assert cc.STATE_TTL_SECONDS == 20 * 60
