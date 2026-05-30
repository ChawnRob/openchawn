"""Unit tests for LLM provider adapters (Phase 1 refactor)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.llm.adapters.deepseek import DeepSeekAdapter, deepseek_model_for_task
from app.llm.adapters.registry import dispatch_adapter, get_adapter
from app.settings import get_settings


def test_deepseek_model_for_task_reasoning_uses_pro():
    with patch.dict("os.environ", {"DEEPSEEK_MODEL": "deepseek-custom-pro"}, clear=False):
        assert deepseek_model_for_task("reasoning") == "deepseek-custom-pro"
    assert deepseek_model_for_task("simple") == "deepseek-v4-flash"


def test_get_adapter_known_names():
    for name in ("deepseek", "kimi", "openai", "infomaniak", "openrouter"):
        assert get_adapter(name) is not None
    assert get_adapter("unknown") is None


def test_dispatch_unknown_provider():
    s = get_settings()
    text, code, err = dispatch_adapter("nope", s, "sys", "user")
    assert text == ""
    assert err == "UNKNOWN_PROVIDER"


def test_deepseek_adapter_missing_key():
    adapter = DeepSeekAdapter()
    s = MagicMock()
    with patch("app.llm.adapters.deepseek.resolve_deepseek_api_key", return_value=""):
        out = adapter.complete(settings=s, system_prompt="s", user_message="u")
    assert out.error == "DEEPSEEK_API_KEY_MISSING"
    assert out.text == ""


def test_openrouter_adapter_delegates_http():
    adapter = get_adapter("openrouter")
    s = MagicMock()
    s.openrouter_base_url = "https://openrouter.ai/api/v1"
    s.openrouter_api_key = "key"
    s.openrouter_model = "openrouter/auto"
    with patch(
        "app.llm.adapters.openrouter.chat_completions",
        return_value=("ok", 200, None),
    ) as mock_cc:
        out = adapter.complete(settings=s, system_prompt="s", user_message="u")
    assert out.text == "ok"
    mock_cc.assert_called_once()
