"""Groq text provider routing — economical default, premium gated."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.files_intake.image_analysis import ImageAnalysisResult, analyze_image_bytes
from app.llm.gateway import generate_response
from app.provider_manager import get_provider_manager, reset_provider_manager_singleton
from app.settings import reload_settings


def _groq_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_TEXT_PROVIDER", "groq")
    monkeypatch.setenv("TEXT_PROVIDER_ORDER", "local,groq,kimi,deepseek,mistral,openai,infomaniak,openrouter")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_groq")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.setenv("ANTHROPIC_ENABLED", "false")
    monkeypatch.setenv("ALLOW_PREMIUM_MODELS", "false")
    monkeypatch.setenv("KIMI_API_KEY", "kimi-test")
    reload_settings()
    reset_provider_manager_singleton()


def _fake_groq_response(text: str = "Réponse Groq rapide.") -> object:
    return type(
        "R",
        (),
        {
            "status_code": 200,
            "ok": True,
            "text": "",
            "json": lambda self: {
                "choices": [{"message": {"content": text}}],
            },
        },
    )()


def test_groq_selected_as_default_text_provider(monkeypatch: pytest.MonkeyPatch):
    _groq_env(monkeypatch)
    pm = get_provider_manager()
    order = pm.resolution_order()
    assert order[0] == "groq"

    posts: list[str] = []

    def _fake_post(url, **kwargs):
        posts.append(url)
        return _fake_groq_response()

    with patch("app.llm.gateway.http_requests.post", side_effect=_fake_post):
        result = generate_response(system_prompt="sys", user_message="Bonjour")

    assert result["success"] is True
    assert result["provider_used"] == "groq"
    assert result["model_used"] == "llama-3.1-8b-instant"
    assert result["fallback_used"] is False
    assert len(posts) == 1
    assert "groq.com" in posts[0]


def test_openai_not_called_when_openai_enabled_false(monkeypatch: pytest.MonkeyPatch):
    _groq_env(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("KIMI_API_KEY", "")
    reload_settings()
    reset_provider_manager_singleton()

    posts: list[str] = []

    def _fake_post(url, **kwargs):
        posts.append(url)
        if "openai.com" in url:
            raise AssertionError("OpenAI should not be called when OPENAI_ENABLED=false")
        return _fake_groq_response()

    # Only deepseek available besides blocked openai
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    reload_settings()
    reset_provider_manager_singleton()

    with patch("app.llm.gateway.http_requests.post", side_effect=_fake_post):
        result = generate_response(system_prompt="sys", user_message="test")

    assert result["success"] is True
    assert result["provider_used"] == "deepseek"
    assert not any("openai.com" in u for u in posts)


def test_premium_fallback_blocked_when_allow_premium_models_false(monkeypatch: pytest.MonkeyPatch):
    _groq_env(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("KIMI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    monkeypatch.setenv("ALLOW_PREMIUM_MODELS", "false")
    reload_settings()
    reset_provider_manager_singleton()

    pm = get_provider_manager()
    assert "openrouter" not in pm.resolution_order()
    assert "openai" not in pm.resolution_order()

    result = generate_response(system_prompt="sys", user_message="test")
    assert result["success"] is False


def test_premium_openrouter_allowed_when_flag_true(monkeypatch: pytest.MonkeyPatch):
    _groq_env(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("KIMI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    monkeypatch.setenv("ALLOW_PREMIUM_MODELS", "true")
    reload_settings()
    reset_provider_manager_singleton()

    posts: list[str] = []

    def _fake_post(url, **kwargs):
        posts.append(url)
        return _fake_groq_response("OpenRouter OK")

    with patch("app.llm.gateway.http_requests.post", side_effect=_fake_post):
        result = generate_response(system_prompt="sys", user_message="premium route")

    assert result["success"] is True
    assert result["provider_used"] == "openrouter"


def test_image_generation_never_called_for_text_chat(monkeypatch: pytest.MonkeyPatch):
    _groq_env(monkeypatch)

    with patch("app.llm.gateway.http_requests.post", return_value=_fake_groq_response()), patch(
        "app.files_intake.image_generation_providers.OpenAIImageGenerationProvider.generate_image"
    ) as gen_mock:
        result = generate_response(system_prompt="sys", user_message="analyse ce texte")

    assert result["success"] is True
    gen_mock.assert_not_called()


def test_image_generation_never_called_for_image_analysis(monkeypatch: pytest.MonkeyPatch):
    mock_result = ImageAnalysisResult(
        description="Capture UI.",
        detected_elements=["bouton"],
        clarification_question=None,
        provider="kimi",
        model="moonshot-v1-8k-vision-preview",
        raw_text="{}",
        fallback_used=False,
    )

    with patch(
        "app.files_intake.image_analysis.vision_provider_configured",
        return_value=True,
    ), patch(
        "app.files_intake.vision_providers.analyze_image_with_provider_routing",
        return_value=mock_result,
    ), patch(
        "app.files_intake.image_generation_providers.OpenAIImageGenerationProvider.generate_image"
    ) as gen_mock:
        from tests.test_files_intake import PNG_MAGIC

        result = analyze_image_bytes(
            payload=PNG_MAGIC + b"\x00" * 8,
            content_type="image/png",
            filename="ui.png",
        )

    assert result.provider == "kimi"
    gen_mock.assert_not_called()


def test_groq_fallback_to_kimi_sets_fallback_used(monkeypatch: pytest.MonkeyPatch):
    _groq_env(monkeypatch)

    def _fake_post(url, **kwargs):
        if "groq.com" in url:
            return type("R", (), {"status_code": 502, "ok": False, "text": "down"})()
        return _fake_groq_response("Réponse Kimi.")

    with patch("app.llm.gateway.http_requests.post", side_effect=_fake_post):
        result = generate_response(system_prompt="sys", user_message="hello")

    assert result["success"] is True
    assert result["provider_used"] == "kimi"
    assert result["fallback_used"] is True
