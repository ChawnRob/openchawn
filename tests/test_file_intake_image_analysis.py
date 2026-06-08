"""File intake image analysis V1 — vision pipeline and API wiring."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.files_intake.image_analysis import (
    ImageAnalysisError,
    ImageAnalysisResult,
    VisionUnavailableError,
    analyze_image_bytes,
)
from app.main import app
from tests.test_files_intake import (
    JPEG_MAGIC,
    PNG_MAGIC,
    _guest_headers,
    _post_intake,
    _reset_guest,
)


def _mock_analysis(**overrides) -> ImageAnalysisResult:
    base = {
        "description": "Une capture d'écran avec un formulaire.",
        "detected_elements": ["bouton Envoyer", "champ texte"],
        "clarification_question": "Souhaitez-vous analyser le texte du formulaire ?",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "raw_text": "{}",
    }
    base.update(overrides)
    return ImageAnalysisResult(**base)


def test_analyze_image_bytes_parses_json_response():
    payload = PNG_MAGIC + b"\x00" * 32
    fake_resp = type(
        "R",
        (),
        {
            "status_code": 200,
            "ok": True,
            "text": "",
            "json": lambda self: {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "description": "Photo d'un chat sur un canapé.",
                                    "detected_elements": ["chat", "canapé"],
                                    "clarification_question": None,
                                }
                            )
                        }
                    }
                ]
            },
        },
    )()

    with patch("app.files_intake.image_analysis.get_settings") as gs, patch(
        "app.files_intake.image_analysis.requests.post", return_value=fake_resp
    ):
        gs.return_value.openai_api_key = "sk-test"
        gs.return_value.openai_base_url = "https://api.openai.com/v1"
        gs.return_value.openai_model = "gpt-4o-mini"
        result = analyze_image_bytes(
            payload=payload, content_type="image/png", filename="cat.png"
        )

    assert "chat" in result.description
    assert result.detected_elements == ["chat", "canapé"]
    assert result.clarification_question is None
    assert "Description :" in result.to_message()
    assert "Éléments détectés" in result.to_message()


def test_intake_image_returns_analysis_in_api_response():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    data = PNG_MAGIC + b"\x00" * 64
    analysis = _mock_analysis()

    with patch("app.api.files_intake.analyze_image_bytes", return_value=analysis):
        r = _post_intake(client, headers, "ui.png", data, "image/png")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "analyzed"
    assert body["analysis_enabled"] is True
    assert body["analysis"]["description"] == analysis.description
    assert body["analysis"]["detected_elements"] == analysis.detected_elements
    assert body["message"] == analysis.to_message()
    assert body["stored"] is False


def test_intake_image_vision_unavailable_returns_503():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    data = JPEG_MAGIC + b"\x00" * 32

    with patch(
        "app.api.files_intake.analyze_image_bytes",
        side_effect=VisionUnavailableError("OPENAI_API_KEY manquante"),
    ):
        r = _post_intake(client, headers, "photo.jpg", data, "image/jpeg")

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["failure_mode"] == "vision_unavailable"
    assert "OPENAI_API_KEY" in detail["message"]


def test_intake_image_analysis_failure_returns_502():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    data = PNG_MAGIC + b"\x00" * 16

    with patch(
        "app.api.files_intake.analyze_image_bytes",
        side_effect=ImageAnalysisError("Réponse vision vide."),
    ):
        r = _post_intake(client, headers, "bad.png", data, "image/png")

    assert r.status_code == 502
    assert r.json()["detail"]["failure_mode"] == "analysis_failed"


def test_intake_txt_skips_vision_analysis():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)

    with patch("app.api.files_intake.analyze_image_bytes") as analyze:
        r = _post_intake(client, headers, "note.txt", b"hello", "text/plain")

    analyze.assert_not_called()
    assert r.status_code == 200
    body = r.json()
    assert body["analysis_enabled"] is False
    assert "uniquement les images" in body["message"]
