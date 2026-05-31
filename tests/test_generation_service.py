"""GenerationService tests — provider order, fallback, no-key paths (Phase 1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.llm.generation_service import GenerationService


def test_generation_fallback_primary_down(monkeypatch):
    pm = MagicMock()
    pm.intelligent_decision.return_value = MagicMock(
        ordered_providers=["deepseek", "openrouter"],
        task_type="general",
    )
    pm.resolution_order.return_value = ["deepseek", "openrouter"]
    monkeypatch.setattr("app.llm.generation_service.get_provider_manager", lambda: pm)
    monkeypatch.setattr("app.llm.generation_service.resolve_deepseek_api_key", lambda: "fake")
    monkeypatch.setattr(
        "app.llm.generation_service.get_fallback_manager",
        lambda: MagicMock(record=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        "app.llm.generation_service.get_provider_health_hooks",
        lambda: MagicMock(mark_success=lambda *a: None, mark_failure=lambda *a: None),
    )
    monkeypatch.setattr(
        "app.llm.generation_service.get_cost_tracking_hooks",
        lambda: MagicMock(track=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        "app.llm.generation_service.get_settings",
        lambda: MagicMock(default_provider="deepseek"),
    )

    def fake_dispatch(name, *args, **kwargs):
        if name == "deepseek":
            return "", 503, "primary unavailable"
        return "secondary ok", 200, None

    monkeypatch.setattr("app.llm.generation_service.dispatch_adapter", fake_dispatch)

    result = GenerationService().generate(system_prompt="sys", user_message="hi")
    assert result.success is True
    assert result.provider == "openrouter"
    assert result.output == "secondary ok"


def test_generation_no_key_configured(monkeypatch):
    pm = MagicMock()
    pm.intelligent_decision.return_value = MagicMock(ordered_providers=[], task_type="general")
    pm.resolution_order.return_value = []
    monkeypatch.setattr("app.llm.generation_service.get_provider_manager", lambda: pm)
    monkeypatch.setattr("app.llm.generation_service.resolve_deepseek_api_key", lambda: None)
    monkeypatch.setattr(
        "app.llm.generation_service.get_settings",
        lambda: MagicMock(default_provider="deepseek"),
    )

    result = GenerationService().generate(system_prompt="sys", user_message="hi")
    assert result.success is False
    assert result.provider == "none"
    assert result.error


def test_generation_openrouter_when_intelligent_order_empty(monkeypatch):
    pm = MagicMock()
    pm.intelligent_decision.return_value = MagicMock(ordered_providers=[], task_type="simple")
    pm.resolution_order.return_value = ["openrouter"]
    monkeypatch.setattr("app.llm.generation_service.get_provider_manager", lambda: pm)
    monkeypatch.setattr("app.llm.generation_service.resolve_deepseek_api_key", lambda: "k")
    monkeypatch.setattr(
        "app.llm.generation_service.get_fallback_manager",
        lambda: MagicMock(record=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        "app.llm.generation_service.get_provider_health_hooks",
        lambda: MagicMock(mark_success=lambda *a: None),
    )
    monkeypatch.setattr(
        "app.llm.generation_service.get_cost_tracking_hooks",
        lambda: MagicMock(track=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        "app.llm.generation_service.get_settings",
        lambda: MagicMock(default_provider="openrouter"),
    )
    monkeypatch.setattr(
        "app.llm.generation_service.dispatch_adapter",
        lambda name, *a, **k: ("router-ok", 200, None) if name == "openrouter" else ("", 503, "fail"),
    )

    result = GenerationService().generate(system_prompt="sys", user_message="hi")
    assert result.success is True
    assert result.provider == "openrouter"


def test_generate_response_dict_shape_unchanged():
    from app.llm.gateway import generate_response
    from app.llm.types import ProviderResult

    fake = ProviderResult(
        output="x",
        provider="mock",
        success=True,
        status_code=200,
        error=None,
    )
    with patch("app.llm.gateway.get_generation_service") as mock_svc:
        mock_svc.return_value.generate.return_value = fake
        out = generate_response(system_prompt="s", user_message="u")
    assert out["output"] == "x"
    assert out["success"] is True
    assert "forced_french_runtime_removed" in out
