"""Mobile image composer flow — attach image + chat in same session."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.chat import ChatRequest, assemble_chat_generation_inputs
from app.files_intake.image_analysis import ImageAnalysisResult
from app.files_intake.session_image_context import (
    clear_image_context_store,
    message_references_recent_image,
    session_key_from_user,
)
from app.main import app
from tests.test_files_intake import PNG_MAGIC, _guest_headers, _post_intake, _reset_guest

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"

_MOCK_ANALYSIS = ImageAnalysisResult(
    description="Formulaire bleu avec bouton Envoyer.",
    detected_elements=["bouton Envoyer", "champ email"],
    clarification_question=None,
    provider="kimi",
    model="moonshot-v1-8k-vision-preview",
    raw_text="{}",
    fallback_used=False,
)


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_frontend_has_pending_image_attachment_state():
    html = _html()
    assert "pendingImageAttachment" in html
    assert "ocAttachImageToComposer" in html
    assert "ocUploadPendingImageAttachment" in html
    assert 'id="ocComposerAttachment"' in html
    assert "Joindre au message" in html


def test_send_uploads_then_chats_with_media_id():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    session_id = headers["X-Guest-Session"]

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS):
        intake = _post_intake(client, headers, "ui.png", PNG_MAGIC + b"\x00" * 16, "image/png")
    assert intake.status_code == 200
    body = intake.json()
    media_id = body["media_id"]
    intake_key = session_key_from_user(
        {"is_guest": True, "guest_session_id": session_id, "ip": "testclient"}
    )

    guest_user = {"is_guest": True, "guest_session_id": session_id, "ip": "testclient"}
    chat_key = session_key_from_user(guest_user)
    assert intake_key == chat_key

    req = ChatRequest(
        message="Que vois-tu sur cette capture ?",
        media_id=media_id,
    )
    bundle = assemble_chat_generation_inputs(
        req, user=guest_user, persist_memory_side_effects=False
    )
    assert bundle["image_context_injected"] is True
    assert _MOCK_ANALYSIS.description in bundle["user_message"]
    assert media_id in bundle["user_message"]


def test_followup_describe_previous_image_uses_context():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS):
        _post_intake(client, headers, "shot.png", PNG_MAGIC + b"\x00" * 8, "image/png")

    guest_user = {
        "is_guest": True,
        "guest_session_id": headers["X-Guest-Session"],
        "ip": "testclient",
    }
    phrase = "Peux-tu décrire l'image précédente ?"
    assert message_references_recent_image(phrase)

    bundle = assemble_chat_generation_inputs(
        ChatRequest(message=phrase),
        user=guest_user,
        persist_memory_side_effects=False,
    )
    assert bundle["image_context_injected"] is True
    assert _MOCK_ANALYSIS.description in bundle["user_message"]


def test_image_reference_phrases_recognized():
    phrases = [
        "image précédente",
        "photo précédente",
        "image envoyée précédemment",
        "photo envoyée précédemment",
        "l'image que je viens d'envoyer",
        "la photo que je viens d'envoyer",
    ]
    for p in phrases:
        assert message_references_recent_image(f"Peux-tu analyser {p} ?"), p


def test_crop_failure_does_not_block_attach_in_frontend():
    html = _html()
    attach_fn = html.split("async function ocAttachImageToComposer")[1].split("async function ocSendFileIntakeDraft")[0]
    assert "crop failed, using original image" in attach_fn
    assert "Recadrage indisponible" in attach_fn
    assert "return;" not in attach_fn.split("catch (err)")[1].split("ocRevokePendingImagePreviewUrl")[0]


def test_send_function_passes_media_id_to_chat():
    html = _html()
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocUploadPendingImageAttachment" in send_fn
    assert "chatBody.media_id" in send_fn
    assert "Peux-tu décrire cette image ?" in send_fn
    assert "pendingIntakeMsg" not in send_fn
