"""File intake image context — session memory for follow-up chat questions."""

from __future__ import annotations

import io
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.chat import ChatRequest, assemble_chat_generation_inputs
from app.files_intake.image_analysis import ImageAnalysisResult
from app.files_intake.session_image_context import (
    build_last_image_context,
    clear_image_context_memory_cache,
    clear_image_context_store,
    message_references_recent_image,
    session_key_from_user,
)
from app.main import app
from tests.test_files_intake import (
    JPEG_MAGIC,
    PNG_MAGIC,
    _guest_headers,
    _post_intake,
    _reset_guest,
)

_MOCK_ANALYSIS_A = ImageAnalysisResult(
    description="Formulaire de connexion bleu.",
    detected_elements=["bouton Envoyer", "label texte Email"],
    clarification_question=None,
    provider="openai",
    model="gpt-4o-mini",
    raw_text="{}",
)

_MOCK_ANALYSIS_B = ImageAnalysisResult(
    description="Chat mobile avec trombone.",
    detected_elements=["bouton trombone", "zone de saisie"],
    clarification_question=None,
    provider="openai",
    model="gpt-4o-mini",
    raw_text="{}",
)


def test_message_references_recent_image_patterns():
    assert message_references_recent_image("Peux-tu m'en dire plus sur la dernière image ?")
    assert message_references_recent_image("Analyse la photo que je viens d'envoyer")
    assert message_references_recent_image("Tell me more about the last image")
    assert message_references_recent_image("peux-tu analyser l'image envoyée précédemment ?")
    assert message_references_recent_image("la photo précédente")
    assert message_references_recent_image("celle que j'ai envoyée")
    assert not message_references_recent_image("Bonjour, comment ça va ?")


def test_upload_then_analyse_image_envoyee_precedemment_injects_context():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    data = PNG_MAGIC + b"\x00" * 32

    with patch(
        "app.api.files_intake.analyze_image_bytes",
        return_value=_MOCK_ANALYSIS_A,
    ):
        intake = _post_intake(client, headers, "form.png", data, "image/png")
    assert intake.status_code == 200
    body = intake.json()

    guest_user = {
        "is_guest": True,
        "guest_session_id": headers["X-Guest-Session"],
        "ip": "testclient",
    }
    req = ChatRequest(message="peux-tu analyser l'image envoyée précédemment ?")
    bundle = assemble_chat_generation_inputs(
        req, user=guest_user, persist_memory_side_effects=False
    )

    assert bundle["image_context_injected"] is True
    assert "LAST IMAGE CONTEXT" in bundle["user_message"]
    assert _MOCK_ANALYSIS_A.description in bundle["user_message"]
    assert body["media_id"] in bundle["user_message"]


def test_image_context_survives_memory_cache_clear():
    """Simulates a different Railway worker: RAM empty, durable store still has context."""
    clear_image_context_store()
    ctx = build_last_image_context(
        filename="x.png",
        mime_type="image/png",
        description="Test persistance.",
        detected_elements=["bouton"],
    )
    key = "guest:worker_sim_session"
    from app.files_intake.session_image_context import set_last_image_context

    set_last_image_context(key, ctx)
    clear_image_context_memory_cache()

    from app.files_intake.session_image_context import get_last_image_context

    loaded = get_last_image_context(key)
    assert loaded is not None
    assert loaded.media_id == ctx.media_id
    assert loaded.description == "Test persistance."


def test_intake_and_chat_use_same_context_key():
    clear_image_context_store()
    guest_user = {"is_guest": True, "guest_session_id": "guest_same_key_1", "ip": "10.0.0.1"}
    assert session_key_from_user(guest_user) == "guest:guest_same_key_1"


def test_upload_then_followup_chat_injects_image_context():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    data = PNG_MAGIC + b"\x00" * 32

    with patch(
        "app.api.files_intake.analyze_image_bytes",
        return_value=_MOCK_ANALYSIS_A,
    ):
        intake = _post_intake(client, headers, "form.png", data, "image/png")
    assert intake.status_code == 200
    body = intake.json()
    assert body.get("media_id", "").startswith("img_")
    assert body["last_image_context"]["description"] == _MOCK_ANALYSIS_A.description

    guest_user = {
        "is_guest": True,
        "guest_session_id": headers["X-Guest-Session"],
        "ip": "testclient",
    }
    req = ChatRequest(message="Peux-tu m'en dire plus sur la dernière image ?")
    bundle = assemble_chat_generation_inputs(
        req, user=guest_user, persist_memory_side_effects=False
    )

    assert bundle["image_context_injected"] is True
    assert "LAST IMAGE CONTEXT" in bundle["user_message"]
    assert _MOCK_ANALYSIS_A.description in bundle["user_message"]
    assert body["media_id"] in bundle["user_message"]
    assert "Do NOT claim you cannot see the image" in bundle["user_message"]


def test_image_question_without_prior_upload_has_no_context():
    clear_image_context_store()
    guest_user = {
        "is_guest": True,
        "guest_session_id": "guest_no_image_ctx",
        "ip": "127.0.0.1",
    }
    req = ChatRequest(message="Peux-tu analyser l'image ?")
    bundle = assemble_chat_generation_inputs(
        req, user=guest_user, persist_memory_side_effects=False
    )

    assert bundle["image_context_injected"] is False
    assert "LAST IMAGE CONTEXT" not in bundle["user_message"]


def test_second_upload_replaces_last_image_context():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    session_id = headers["X-Guest-Session"]

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS_A):
        r1 = _post_intake(client, headers, "a.png", PNG_MAGIC + b"\x00" * 16, "image/png")
    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS_B):
        r2 = _post_intake(client, headers, "b.jpg", JPEG_MAGIC + b"\x00" * 16, "image/jpeg")

    assert r1.status_code == 200
    assert r2.status_code == 200
    media_b = r2.json()["media_id"]

    guest_user = {"is_guest": True, "guest_session_id": session_id, "ip": "testclient"}
    req = ChatRequest(message="Analyse la dernière image")
    bundle = assemble_chat_generation_inputs(
        req, user=guest_user, persist_memory_side_effects=False
    )

    assert bundle["image_context_injected"] is True
    assert _MOCK_ANALYSIS_B.description in bundle["user_message"]
    assert _MOCK_ANALYSIS_A.description not in bundle["user_message"]
    assert media_b in bundle["user_message"]


def test_handle_chat_request_uses_image_context_end_to_end():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS_A):
        intake = _post_intake(client, headers, "ui.png", PNG_MAGIC + b"\x00" * 8, "image/png")
    assert intake.status_code == 200

    captured: dict = {}

    def _fake_gen(**kwargs):
        captured.update(kwargs)
        return {
            "output": "Je vois le formulaire bleu avec un bouton Envoyer.",
            "success": True,
            "provider": "mock",
            "status_code": 200,
        }

    with patch("app.api.chat.generate_response", side_effect=_fake_gen), patch(
        "app.api.chat.write_exchange",
        return_value=type("R", (), {"saved": False, "reason": "test"})(),
    ):
        r = client.post(
            "/chat",
            json={"message": "Dis m'en plus sur la photo que je viens d'envoyer"},
            headers=headers,
        )

    assert r.status_code == 200, r.text
    assert "LAST IMAGE CONTEXT" in captured.get("user_message", "")
    assert _MOCK_ANALYSIS_A.description in captured.get("user_message", "")
