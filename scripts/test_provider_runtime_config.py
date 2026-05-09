#!/usr/bin/env python3
"""Tests chargement provider runtime (aliases clés, gateway, endpoint safe sans fuite)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_HEALTH_KEYS = frozenset(
    {
        "selected_provider",
        "provider_manager_path",
        "deepseek_key_present",
        "openrouter_key_present",
        "openai_key_present",
        "deepseek_model_present",
        "base_url_present",
        "env_names_checked",
        "runtime_config_source",
    }
)


def _snapshot(keys: tuple[str, ...]) -> dict[str, str | None]:
    return {k: os.environ.get(k) for k in keys}


def _restore(snap: dict[str, str | None]) -> None:
    for k, v in snap.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _reset_runtime() -> None:
    from app.provider_manager import reset_provider_manager_singleton
    from app.settings import reload_settings

    reload_settings()
    reset_provider_manager_singleton()


def _no_secret_leak(obj: object) -> None:
    blob = json.dumps(obj, default=str)
    low = blob.lower()
    assert "sk-" not in low
    assert "sk_" not in low


def _clear_deepseek_env() -> None:
    from app.provider_runtime_config import DEEPSEEK_API_KEY_ENV_ALIASES

    for k in DEEPSEEK_API_KEY_ENV_ALIASES:
        os.environ.pop(k, None)


def _clear_other_llm_keys() -> None:
    """Isole les scénarios de test du .env local (OpenAI avant OpenRouter dans FIXED_ORDER)."""
    for k in ("OPENAI_API_KEY", "KIMI_API_KEY", "INFOMANIAK_API_KEY"):
        os.environ.pop(k, None)


def main() -> int:
    from fastapi.testclient import TestClient

    from app.llm.gateway import generate_response
    from app.main import app
    from app.provider_runtime_config import get_provider_runtime_config

    keys = (
        "OPENCHAWN_ENV",
        "SECRET_KEY",
        "DEFAULT_PROVIDER",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_KEY",
        "DEEPSEEK_TOKEN",
        "OPENCHAWN_DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "OPEN_ROUTER_API_KEY",
        "OPENAI_API_KEY",
        "KIMI_API_KEY",
        "INFOMANIAK_API_KEY",
    )
    snap = _snapshot(keys)

    try:
        # production : évite load_dotenv qui remplacerait les clés qu'on a volontairement ôtées du OS env
        os.environ["OPENCHAWN_ENV"] = "production"
        os.environ["SECRET_KEY"] = "test-runtime-provider-secret-xxxxx"

        # 1) GET /health/provider-runtime : forme fixe, pas de fuite
        _clear_deepseek_env()
        _clear_other_llm_keys()
        os.environ.pop("OPEN_ROUTER_API_KEY", None)
        os.environ["OPENROUTER_API_KEY"] = "or-test-placeholder"
        os.environ["DEFAULT_PROVIDER"] = "deepseek"
        _reset_runtime()

        client = TestClient(app)
        r = client.get("/health/provider-runtime")
        assert r.status_code == 200, r.text
        body = r.json()
        assert EXPECTED_HEALTH_KEYS == set(body.keys()), sorted(body.keys())
        _no_secret_leak(body)
        assert body["deepseek_key_present"] is False
        assert body["openrouter_key_present"] is True
        assert isinstance(body["env_names_checked"], list)

        cfg = get_provider_runtime_config()
        from app.provider_manager import get_provider_manager

        assert cfg["selected_provider"] == get_provider_manager().active_provider()

        # 3) Alias DEEPSEEK_KEY : generate_response utilise DeepSeek, pas d'erreur « missing » précoce
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("OPEN_ROUTER_API_KEY", None)
        _clear_other_llm_keys()
        _clear_deepseek_env()
        os.environ["DEEPSEEK_KEY"] = "deepseek-alias-test"
        os.environ["DEFAULT_PROVIDER"] = "deepseek"
        _reset_runtime()

        with patch("app.llm.gateway._chat_completions", return_value=("hello", 200, None)):
            out = generate_response(system_prompt="s", user_message="user test", provider_hint="")
        assert out.get("success") is True, out
        assert out.get("provider") == "deepseek"
        assert "missing" not in str(out.get("error") or "").lower()

        # 4) Pas de clé DeepSeek native ; OpenRouter seul : pas de « DeepSeek API key missing »
        _clear_deepseek_env()
        _clear_other_llm_keys()
        os.environ["OPENROUTER_API_KEY"] = "openrouter-only-test"
        os.environ["DEFAULT_PROVIDER"] = "deepseek"
        _reset_runtime()

        pm = get_provider_manager()
        assert pm.resolution_order() and pm.resolution_order()[0] == "openrouter", pm.resolution_order()

        def _fake_dispatch(name, s, system_prompt, user_message, task_type=""):
            if name == "openrouter":
                return ("okrouter", 200, None)
            return "", None, "skip"

        with patch("app.llm.gateway._dispatch", side_effect=_fake_dispatch):
            out2 = generate_response(system_prompt="s", user_message="user", provider_hint="")
        assert out2.get("success") is True, out2
        assert out2.get("provider") == "openrouter"
        err2 = str(out2.get("error") or "")
        assert "DeepSeek API key missing" not in err2

    finally:
        _restore(snap)
        _reset_runtime()

    print("OK test_provider_runtime_config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
