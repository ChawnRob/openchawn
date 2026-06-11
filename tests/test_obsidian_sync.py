"""Obsidian optional sync — status API and UI contract."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_obsidian_sync_defaults_disabled():
    from app.core.obsidian_sync import get_obsidian_sync_status

    st = get_obsidian_sync_status()
    assert st["enabled"] is False
    assert st["sync_enabled"] is False
    assert st["mode"] == "uri"
    assert st["vault_name"] == "OpenChawn"
    assert st["default_folder"] == "COCO"
    assert st["uri_open_available"] is False


def test_obsidian_sync_enabled_uri_without_deep_sync(monkeypatch):
    from app.core.obsidian_sync import get_obsidian_sync_status

    monkeypatch.setenv("OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("OBSIDIAN_SYNC_ENABLED", "false")
    monkeypatch.setenv("OBSIDIAN_MODE", "uri")
    st = get_obsidian_sync_status()
    assert st["enabled"] is True
    assert st["sync_enabled"] is False
    assert st["uri_open_available"] is True


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
    assert data["enabled"] is False
    assert data["sync_enabled"] is False
    assert "token" not in str(data).lower()
    assert "27124" not in str(data)


def test_ui_affine_and_obsidian_chips_separate():
    html = _html()
    assert "Ouvrir AFFiNE" in html
    assert "Sync Obsidian" in html
    assert 'data-coco-action="open-affine-second-brain"' in html
    assert 'data-coco-action="open-obsidian-sync"' in html
    assert "coco-obsidian-sync-btn" in html
    assert "coco-second-brain-btn" in html


def test_ui_no_false_obsidian_sync_success_messages():
    html = _html()
    obsidian_fn = html.split("function ocHandleObsidianSyncClick")[1].split("document.addEventListener('click'")[0]
    assert "note synchronisée" not in obsidian_fn
    assert "écrit dans Obsidian" not in obsidian_fn
    assert "sync réussie" not in obsidian_fn
    assert "OC_OBSIDIAN_NOT_CONFIGURED_FR" in html
    assert "pas encore configur" in html
    assert "/api/obsidian-sync/status" in html
    assert "obsidian://new" in html


def test_affine_open_path_unchanged():
    html = _html()
    open_fn = html.split("function ocOpenAffineSecondBrain")[1].split("var ocObsidianSyncConfig")[0]
    assert "window.location.href" not in open_fn
    assert "window.open(affineUrl" in open_fn
