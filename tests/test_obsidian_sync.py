"""Obsidian optional sync — status API and UI contract."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _obsidian_block() -> str:
    html = _html()
    return html.split("var ocObsidianSyncConfig")[1].split("document.getElementById('cocoPromptChips')")[0]


def test_obsidian_sync_defaults_uri_enabled():
    from app.core.obsidian_sync import get_obsidian_sync_status

    st = get_obsidian_sync_status()
    assert st["enabled"] is True
    assert st["sync_enabled"] is False
    assert st["mode"] == "uri"
    assert st["vault_name"] == "OpenChawn"
    assert st["default_folder"] == "COCO"
    assert st["uri_open_available"] is True


def test_obsidian_sync_can_be_disabled(monkeypatch):
    from app.core.obsidian_sync import get_obsidian_sync_status

    monkeypatch.setenv("OBSIDIAN_ENABLED", "false")
    st = get_obsidian_sync_status()
    assert st["enabled"] is False
    assert st["uri_open_available"] is False


def test_api_obsidian_sync_status_no_secrets():
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/obsidian-sync/status")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "enabled",
        "mode",
        "vault_name",
        "default_folder",
        "sync_enabled",
        "configured",
        "uri_open_available",
    }
    assert data["enabled"] is True
    assert data["sync_enabled"] is False
    assert "token" not in str(data).lower()
    assert "27124" not in str(data)
    assert "OBSIDIAN_LOCAL_REST_API_TOKEN" not in _html()


def test_ui_affine_and_obsidian_chips_separate():
    html = _html()
    assert "Ouvrir AFFiNE" in html
    assert "Sync Obsidian" in html
    assert 'data-coco-action="open-affine-second-brain"' in html
    assert 'data-coco-action="open-obsidian-sync"' in html
    assert "coco-obsidian-sync-btn" in html
    assert "coco-second-brain-btn" in html


def test_oc_sync_obsidian_builds_uri_with_encoded_content():
    block = _obsidian_block()
    assert "function ocSyncObsidian" in _html()
    assert "obsidian://new?vault=" in block
    assert "&name=" in block
    assert "&content=" in block
    assert "encodeURIComponent(markdown)" in block
    assert "ocBuildObsidianNoteMarkdown" in block


def test_ui_no_false_obsidian_sync_success_messages():
    block = _obsidian_block()
    assert "note synchronisée" not in block
    assert "écrit dans Obsidian" not in block
    assert "sync réussie" not in block
    assert "Synchronisation réussie" not in block
    assert "Obsidian sync complete" not in block
    assert "OC_OBSIDIAN_URI_OPENED_FR" in _html()
    assert "/api/obsidian-sync/status" in _html()


def test_oc_sync_obsidian_in_flight_guard():
    block = _obsidian_block()
    assert "ocObsidianOpenInFlight" in block
    assert "800" in block


def test_affine_open_path_unchanged():
    html = _html()
    open_fn = html.split("function ocOpenAffineSecondBrain")[1].split("var ocObsidianSyncConfig")[0]
    assert "window.location.href" not in open_fn
    assert "window.open(affineUrl" in open_fn
