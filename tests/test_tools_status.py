"""GET /api/tools/status — runtime tool exposure."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.settings import reload_settings


def test_tools_status_disabled_without_key(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    reload_settings()

    client = TestClient(app)
    r = client.get("/api/tools/status")
    assert r.status_code == 200
    ws = r.json()["web_search"]
    assert ws["enabled"] is False
    assert ws["configured"] is False
    assert ws["provider"] == "perplexity"


def test_tools_status_enabled_when_configured(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pk-test")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "perplexity")
    reload_settings()

    client = TestClient(app)
    r = client.get("/api/tools/status")
    assert r.status_code == 200
    ws = r.json()["web_search"]
    assert ws["enabled"] is True
    assert ws["configured"] is True
    assert ws["provider"] == "perplexity"
    assert ws["max_results"] == 5
