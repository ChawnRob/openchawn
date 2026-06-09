"""Progressive image analysis provider routing — kimi default, openai fallback."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.files_intake.image_analysis import (
    ImageAnalysisError,
    ImageAnalysisResult,
    VisionUnavailableError,
    analyze_image_bytes,
)
from app.main import app
from tests.test_files_intake import PNG_MAGIC, _guest_headers, _post_intake, _reset_guest


def _vision_json_response(description: str = "Vue aérienne.") -> object:
    return type(
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
                                    "description": description,
                                    "detected_elements": ["ciel", "sol"],
                                    "clarification_question": None,
                                }
                            )
                        }
                    }
                ]
            },
        },
    )()


def _routing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_ANALYSIS_PROVIDER_ORDER", "local,kimi,openai")
    monkeypatch.setenv("IMAGE_ANALYSIS_DEFAULT_PROVIDER", "kimi")
    monkeypatch.setenv("IMAGE_ANALYSIS_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "openai")
    monkeypatch.setenv("KIMI_API_KEY", "test-kimi-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("FILE_INTAKE_VISION_PROVIDER", raising=False)
    from app.settings import reload_settings

    reload_settings()


def test_default_provider_is_kimi_not_openai(monkeypatch: pytest.MonkeyPatch):
    _routing_env(monkeypatch)
    from app.files_intake.vision_providers import image_analysis_default_provider, resolve_vision_provider_id

    assert image_analysis_default_provider() == "kimi"
    assert resolve_vision_provider_id() == "kimi"


def test_analyze_image_uses_kimi_when_default_kimi(monkeypatch: pytest.MonkeyPatch):
    _routing_env(monkeypatch)
    payload = PNG_MAGIC + b"\x00" * 24
    posts: list[str] = []

    def _fake_post(url, **kwargs):
        posts.append(url)
        return _vision_json_response("Analyse Kimi.")

    mock_settings = MagicMock()
    mock_settings.kimi_effective_key = "kimi-test-key"
    mock_settings.kimi_effective_base = "https://api.moonshot.ai/v1"
    mock_settings.image_analysis_kimi_model = "moonshot-v1-8k-vision-preview"
    mock_settings.openai_api_key = "sk-openai-should-not-be-used"
    mock_settings.openai_base_url = "https://api.openai.com/v1"
    mock_settings.image_analysis_openai_model = ""
    mock_settings.openai_model = "gpt-4o-mini"
    mock_settings.image_analysis_provider_order = "local,kimi,openai"
    mock_settings.image_analysis_default_provider = "kimi"
    mock_settings.image_analysis_fallback_provider = "openai"

    with patch("app.files_intake.vision_providers.get_settings", return_value=mock_settings), patch(
        "app.files_intake.vision_providers.requests.post", side_effect=_fake_post
    ):
        result = analyze_image_bytes(
            payload=payload, content_type="image/png", filename="scene.png"
        )

    assert result.provider == "kimi"
    assert result.fallback_used is False
    assert len(posts) == 1
    assert "moonshot.ai" in posts[0]
    assert "openai.com" not in posts[0]


def test_fallback_openai_when_kimi_fails(monkeypatch: pytest.MonkeyPatch):
    _routing_env(monkeypatch)
    payload = PNG_MAGIC + b"\x00" * 24
    call_urls: list[str] = []

    def _fake_post(url, **kwargs):
        call_urls.append(url)
        if "moonshot" in url:
            return type("R", (), {"status_code": 502, "ok": False, "text": "bad gateway"})()
        return _vision_json_response("Analyse OpenAI fallback.")

    mock_settings = MagicMock()
    mock_settings.kimi_effective_key = "kimi-test-key"
    mock_settings.kimi_effective_base = "https://api.moonshot.ai/v1"
    mock_settings.image_analysis_kimi_model = "moonshot-v1-8k-vision-preview"
    mock_settings.openai_api_key = "sk-openai-fallback"
    mock_settings.openai_base_url = "https://api.openai.com/v1"
    mock_settings.image_analysis_openai_model = "gpt-4o-mini"
    mock_settings.openai_model = "gpt-4o-mini"
    mock_settings.image_analysis_provider_order = "local,kimi,openai"
    mock_settings.image_analysis_default_provider = "kimi"
    mock_settings.image_analysis_fallback_provider = "openai"

    with patch("app.files_intake.vision_providers.get_settings", return_value=mock_settings), patch(
        "app.files_intake.vision_providers.requests.post", side_effect=_fake_post
    ):
        result = analyze_image_bytes(
            payload=payload, content_type="image/png", filename="doc.png"
        )

    assert result.provider == "openai"
    assert result.fallback_used is True
    assert len(call_urls) == 2
    assert "moonshot" in call_urls[0]
    assert "openai.com" in call_urls[1]


def test_image_generation_never_called_during_analysis(monkeypatch: pytest.MonkeyPatch):
    _routing_env(monkeypatch)
    payload = PNG_MAGIC + b"\x00" * 16

    mock_analysis = ImageAnalysisResult(
        description="OK",
        detected_elements=[],
        clarification_question=None,
        provider="kimi",
        model="moonshot-v1-8k-vision-preview",
        raw_text="{}",
        fallback_used=False,
    )

    with patch(
        "app.files_intake.vision_providers.analyze_image_with_provider_routing",
        return_value=mock_analysis,
    ), patch(
        "app.files_intake.image_generation_providers.OpenAIImageGenerationProvider.generate_image"
    ) as gen_mock:
        result = analyze_image_bytes(
            payload=payload, content_type="image/png", filename="x.png"
        )

    assert result.provider == "kimi"
    gen_mock.assert_not_called()


def test_intake_response_includes_provider_used(monkeypatch: pytest.MonkeyPatch):
    _routing_env(monkeypatch)
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    analysis = ImageAnalysisResult(
        description="Interface mobile.",
        detected_elements=["bouton"],
        clarification_question=None,
        provider="kimi",
        model="moonshot-v1-8k-vision-preview",
        raw_text="{}",
        fallback_used=False,
    )

    with patch("app.api.files_intake.analyze_image_bytes", return_value=analysis):
        r = _post_intake(client, headers, "ui.png", PNG_MAGIC + b"\x00" * 8, "image/png")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_used"] == "kimi"
    assert body["model_used"] == "moonshot-v1-8k-vision-preview"
    assert body["fallback_used"] is False
    assert body["analysis"]["provider_used"] == "kimi"


def test_high_accuracy_uses_openai_first(monkeypatch: pytest.MonkeyPatch):
    _routing_env(monkeypatch)
    payload = PNG_MAGIC + b"\x00" * 8
    posts: list[str] = []

    def _fake_post(url, **kwargs):
        posts.append(url)
        return _vision_json_response("Haute précision.")

    mock_settings = MagicMock()
    mock_settings.kimi_effective_key = "kimi-key"
    mock_settings.kimi_effective_base = "https://api.moonshot.ai/v1"
    mock_settings.image_analysis_kimi_model = "moonshot-v1-8k-vision-preview"
    mock_settings.openai_api_key = "sk-openai"
    mock_settings.openai_base_url = "https://api.openai.com/v1"
    mock_settings.image_analysis_openai_model = "gpt-4o-mini"
    mock_settings.openai_model = "gpt-4o-mini"
    mock_settings.image_analysis_provider_order = "local,kimi,openai"
    mock_settings.image_analysis_default_provider = "kimi"
    mock_settings.image_analysis_fallback_provider = "openai"

    with patch("app.files_intake.vision_providers.get_settings", return_value=mock_settings), patch(
        "app.files_intake.vision_providers.requests.post", side_effect=_fake_post
    ):
        result = analyze_image_bytes(
            payload=payload,
            content_type="image/png",
            filename="precise.png",
            accuracy_level="high_accuracy",
        )

    assert result.provider == "openai"
    assert len(posts) == 1
    assert "openai.com" in posts[0]


def test_all_providers_fail_raises_vision_unavailable(monkeypatch: pytest.MonkeyPatch):
    _routing_env(monkeypatch)
    mock_settings = MagicMock()
    mock_settings.kimi_effective_key = ""
    mock_settings.openai_api_key = ""
    mock_settings.image_analysis_provider_order = "local,kimi,openai"
    mock_settings.image_analysis_default_provider = "kimi"
    mock_settings.image_analysis_fallback_provider = "openai"

    with patch("app.files_intake.vision_providers.get_settings", return_value=mock_settings):
        with pytest.raises(VisionUnavailableError):
            analyze_image_bytes(
                payload=PNG_MAGIC + b"\x00" * 4,
                content_type="image/png",
                filename="empty.png",
            )
