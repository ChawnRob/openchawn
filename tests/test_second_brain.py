"""Second Brain runtime — status API and COCO prompt injection."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_second_brain_status_safe_defaults():
    from app.core.second_brain import get_second_brain_status

    st = get_second_brain_status()
    assert st["provider"] == "AFFiNE"
    assert st["mode"] == "local-first"
    assert st["ownership"] == "user-owned"
    assert st["api_sync_active"] is False
    assert st["openchawn_document_storage_default"] is False
    assert st["consent_required_for_sync"] is True
    assert st["open_action_configured"] is True
    assert "open_affine" in st["supported_actions_current"]
    assert "read_workspace" in st["supported_actions_future"]


def test_is_affine_api_sync_active_false_by_default(monkeypatch):
    from app.core.second_brain import is_affine_api_sync_active

    monkeypatch.delenv("OPENCHAWN_AFFINE_API_SYNC_ACTIVE", raising=False)
    assert is_affine_api_sync_active() is False


def test_build_second_brain_context_principles():
    from app.core.second_brain import build_second_brain_context

    ctx = build_second_brain_context()
    low = ctx.lower()
    assert "local-first" in low
    assert "user-owned" in low
    assert "not store user documents" in low or "does not store user documents" in low
    assert "api sync is not active" in low
    assert "affine (user-owned workspace)" in low
    assert "est-ce que tu peux gérer mon espace affine" in low
    assert "using affine (not « second brain »)" in low
    assert "never claim affine was opened" in low
    assert "appuyez sur le bouton ouvrir affine" in low
    assert "affine est lancé" in low


def test_coco_system_prompt_includes_second_brain():
    from app.api.chat import build_openchawn_base_system_prompt

    prompt = build_openchawn_base_system_prompt()
    assert "SECOND_BRAIN_RUNTIME_MARKER" in prompt
    assert "api_sync_active" in prompt.lower() or "api sync is not active" in prompt.lower()
    assert "AFFiNE" in prompt


def test_api_second_brain_status_endpoint():
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/second-brain/status")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "provider",
        "mode",
        "ownership",
        "open_action_configured",
        "api_sync_active",
        "openchawn_document_storage_default",
        "consent_required_for_sync",
    }
    assert data["api_sync_active"] is False
    assert data["openchawn_document_storage_default"] is False
    assert "url" not in str(data).lower()
    assert "secret" not in str(data).lower()
