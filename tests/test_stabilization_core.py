"""Stabilization core — chat routes, provider fallback, memory safety, runtime audit."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _mock_llm(**kwargs):
    return {
        "output": "Mock stabilization reply.",
        "success": True,
        "provider": "mock",
        "status_code": 200,
        "forced_french_runtime_removed": False,
        "prompt_contains_forced_french_before_sanitize": False,
    }


def _guest_headers(client: TestClient) -> dict[str, str]:
    sg = client.post("/guest/session", json={})
    assert sg.status_code == 200, sg.text
    return {"X-Guest-Session": sg.json()["session_id"]}


def test_post_chat_responds_with_mock_llm():
    from app.main import app

    client = TestClient(app)
    hdr = _guest_headers(client)

    with patch("app.api.chat.generate_response", side_effect=_mock_llm):
        r = client.post("/chat?debug=true", json={"message": "Hello"}, headers=hdr)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("output") == "Mock stabilization reply."
    assert body.get("provider_used") == "mock"


def test_chat_and_api_chat_routes_stay_coherent():
    from app.main import app

    client = TestClient(app)
    hdr_chat = _guest_headers(client)
    hdr_api = _guest_headers(client)
    payload = {"message": "Ping coherence check"}

    with patch("app.api.chat.generate_response", side_effect=_mock_llm):
        r_chat = client.post("/chat", json=payload, headers=hdr_chat)
        r_api = client.post("/api/chat", json=payload, headers=hdr_api)

    assert r_chat.status_code == 200, r_chat.text
    assert r_api.status_code == 200, r_api.text
    assert r_chat.json().get("output") == r_api.json().get("output")
    assert r_chat.json().get("route_signature") != r_api.json().get("route_signature")


def test_provider_fallback_when_primary_unavailable(monkeypatch):
    from app.llm.gateway import generate_response

    pm = MagicMock()
    pm.intelligent_decision.return_value = MagicMock(
        ordered_providers=["deepseek", "openrouter"],
        task_type="general",
    )
    pm.resolution_order.return_value = ["deepseek", "openrouter"]
    monkeypatch.setattr("app.llm.gateway.get_provider_manager", lambda: pm)
    monkeypatch.setattr("app.llm.gateway.resolve_deepseek_api_key", lambda: "fake-key")
    monkeypatch.setattr(
        "app.llm.gateway.get_fallback_manager",
        lambda: MagicMock(record=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        "app.llm.gateway.get_provider_health_hooks",
        lambda: MagicMock(mark_success=lambda *a: None),
    )
    monkeypatch.setattr(
        "app.llm.gateway.get_cost_tracking_hooks",
        lambda: MagicMock(track=lambda *a, **k: None),
    )

    def fake_dispatch(name, *args, **kwargs):
        if name == "deepseek":
            return "", 503, "primary unavailable"
        return "secondary ok", 200, None

    monkeypatch.setattr("app.llm.gateway._dispatch", fake_dispatch)

    result = generate_response(system_prompt="sys", user_message="hi")
    assert result["success"] is True
    assert result["provider"] == "openrouter"
    assert result["output"] == "secondary ok"


def test_no_provider_configured_returns_clean_failure_without_crash(monkeypatch):
    from app.llm.gateway import generate_response
    from app.main import app

    pm = MagicMock()
    pm.intelligent_decision.return_value = MagicMock(ordered_providers=[], task_type="general")
    pm.resolution_order.return_value = []
    monkeypatch.setattr("app.llm.gateway.get_provider_manager", lambda: pm)
    monkeypatch.setattr("app.llm.gateway.resolve_deepseek_api_key", lambda: None)
    monkeypatch.setattr(
        "app.llm.gateway.get_settings",
        lambda: MagicMock(default_provider="deepseek"),
    )

    result = generate_response(system_prompt="sys", user_message="hi")
    assert result["success"] is False
    assert result["provider"] == "none"
    assert result.get("error")

    client = TestClient(app)
    hdr = _guest_headers(client)
    fail = {
        "output": "",
        "success": False,
        "provider": "none",
        "status_code": None,
        "error": "Aucune clé API LLM configurée",
        "forced_french_runtime_removed": False,
        "prompt_contains_forced_french_before_sanitize": False,
    }
    with patch("app.api.chat.generate_response", return_value=fail):
        r = client.post("/chat", json={"message": "Hello"}, headers=hdr)
    assert r.status_code == 503
    assert "Provider indisponible" in r.json().get("detail", "")


def test_empty_memory_context_does_not_crash(monkeypatch):
    from app.memory.fractal_memory import build_layered_memory_context

    monkeypatch.setattr("app.memory.fractal_memory._load_entries", lambda: [])

    ctx, items = build_layered_memory_context(
        "hello",
        user_key="guest-stabilization",
        is_guest=True,
        persist_memory_side_effects=False,
    )
    assert isinstance(ctx, str)
    assert isinstance(items, list)


def test_api_memory_runtime_status_ok_without_secrets():
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/memory/runtime-status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "database_configured" in data
    assert "fractal_memory_backend" in data
    assert "memory_read_write_verified" in data
    blob = str(data).lower()
    for forbidden in ("password", "secret", "api_key", "token", "postgresql://"):
        assert forbidden not in blob
