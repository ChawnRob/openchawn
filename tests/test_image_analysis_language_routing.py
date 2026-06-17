"""Image/file analysis chat — response language follows latest user message."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.chat import ChatRequest, assemble_chat_generation_inputs
from app.core.language_policy import (
    build_vision_response_language_instruction,
    derive_response_language_trace,
    message_for_language_policy,
    strip_file_metadata_for_language_detection,
)
from app.files_intake.image_analysis import ImageAnalysisResult
from app.files_intake.session_image_context import clear_image_context_store
from app.main import app
from tests.test_files_intake import PNG_MAGIC, _guest_headers, _post_intake, _reset_guest

_MOCK_ANALYSIS = ImageAnalysisResult(
    description="Blue login form with a Send button.",
    detected_elements=["Send button", "email field"],
    clarification_question=None,
    provider="openai",
    model="gpt-4o-mini",
    raw_text="{}",
)


def test_french_image_analysis_request_detects_french():
    trace = derive_response_language_trace("Analyse moi cette image")
    assert trace["response_language_mode"] == "auto"
    assert trace["detected_language"] == "fr"
    assert trace["final_language"] == "fr"


def test_english_image_analysis_request_detects_english():
    trace = derive_response_language_trace("Analyze this image")
    assert trace["response_language_mode"] == "auto"
    assert trace["detected_language"] == "en"
    assert trace["final_language"] == "en"


def test_explicit_english_override_on_french_image_request():
    trace = derive_response_language_trace("Analyse cette image et réponds en anglais")
    assert trace["response_language_mode"] == "explicit"
    assert trace["final_language"] == "en"


def test_translate_image_description_into_french():
    trace = derive_response_language_trace("Translate this image description into French")
    assert trace["response_language_mode"] == "translate"
    assert trace["final_language"] == "fr"


def test_image_metadata_does_not_affect_language_detection():
    raw = "Analyse moi cette image\n[Image : photo.jpg]"
    stripped = strip_file_metadata_for_language_detection(raw)
    assert stripped == "Analyse moi cette image"
    assert message_for_language_policy(raw) == "Analyse moi cette image"
    trace = derive_response_language_trace(raw)
    assert trace["final_language"] == "fr"
    trace_en = derive_response_language_trace("Analyze this image [Image: screenshot.png]")
    assert trace_en["final_language"] == "en"


def test_image_chat_injects_french_vision_language_instruction():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS):
        intake = _post_intake(client, headers, "ui.png", PNG_MAGIC + b"\x00" * 16, "image/png")
    assert intake.status_code == 200
    media_id = intake.json()["media_id"]

    guest_user = {
        "is_guest": True,
        "guest_session_id": headers["X-Guest-Session"],
        "ip": "testclient",
    }
    bundle = assemble_chat_generation_inputs(
        ChatRequest(message="Analyse moi cette image", media_id=media_id),
        user=guest_user,
        persist_memory_side_effects=False,
    )
    assert bundle["image_context_injected"] is True
    assert bundle["target_language"] == "fr"
    assert bundle["response_language_mode"] == "auto"
    assert "Réponds en français" in bundle["lang_instruction"]
    assert "vision" in bundle["lang_instruction"].lower()
    assert _MOCK_ANALYSIS.description in bundle["user_message"]


def test_image_chat_injects_english_vision_language_instruction():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS):
        intake = _post_intake(client, headers, "ui.png", PNG_MAGIC + b"\x00" * 12, "image/png")
    assert intake.status_code == 200
    media_id = intake.json()["media_id"]

    guest_user = {
        "is_guest": True,
        "guest_session_id": headers["X-Guest-Session"],
        "ip": "testclient",
    }
    bundle = assemble_chat_generation_inputs(
        ChatRequest(message="Analyze this image", media_id=media_id),
        user=guest_user,
        persist_memory_side_effects=False,
    )
    assert bundle["target_language"] == "en"
    assert "Respond in English" in bundle["lang_instruction"]
    assert "vision summary" in bundle["lang_instruction"].lower()


def test_explicit_english_on_image_chat_overrides_french_surface():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS):
        intake = _post_intake(client, headers, "ui.png", PNG_MAGIC + b"\x00" * 10, "image/png")
    media_id = intake.json()["media_id"]
    guest_user = {
        "is_guest": True,
        "guest_session_id": headers["X-Guest-Session"],
        "ip": "testclient",
    }
    bundle = assemble_chat_generation_inputs(
        ChatRequest(message="Analyse cette image et réponds en anglais", media_id=media_id),
        user=guest_user,
        persist_memory_side_effects=False,
    )
    assert bundle["response_language_mode"] == "explicit"
    assert bundle["target_language"] == "en"
    assert "Respond in English" in bundle["lang_instruction"]


def test_build_vision_response_language_instruction_contract():
    assert "français" in build_vision_response_language_instruction("fr").lower()
    assert "english" in build_vision_response_language_instruction("en").lower()
    assert "español" in build_vision_response_language_instruction("es").lower()
