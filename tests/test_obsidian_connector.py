"""Obsidian connector — uri_handoff, local_rest, API, and UI contracts."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _normalize_obsidian_intent_text(text: str) -> str:
    t = str(text or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\u2019", "'").replace("'", "'")
    return re.sub(r"\s+", " ", t).strip()


def _detect_obsidian_note_intent(text: str) -> bool:
    t = _normalize_obsidian_intent_text(text)
    if not t or not re.search(r"\bobsidian\b", t):
        return False
    patterns = [
        r"\bnote\s+(ca\s+)?dans\s+obsidian\b",
        r"\bsynchronis\w*\s+(ca|cela|ça)\s+dans\s+obsidian\b",
        r"\benregistr\w*\s+(cette\s+)?conversation\s+dans\s+obsidian\b",
        r"\bajout\w*\s+(ce\s+)?resume\s+(a|à)\s+obsidian\b",
    ]
    return any(re.search(p, t) for p in patterns)


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def test_uri_handoff_creates_obsidian_new_button():
    from app.integrations.obsidian.connector import create_obsidian_note

    with patch.dict(
        "os.environ",
        {"OBSIDIAN_SYNC_MODE": "uri_handoff", "OBSIDIAN_DEFAULT_VAULT": "OpenChawn"},
        clear=False,
    ):
        result = create_obsidian_note(
            title="COCO-test",
            markdown="# Hello",
            folder="COCO",
            source="chat",
        )
    assert result["ok"] is True
    assert result["mode"] == "uri_handoff"
    assert result["uri"].startswith("obsidian://new")
    assert "content=" in result["uri"] or "name=" in result["uri"]

    html = _html()
    assert "ocBuildObsidianSyncButton" in html
    assert "data-obsidian-uri" in html
    assert "obsidian://new" in html


def test_local_rest_writes_note_via_mocked_api(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_resp.text = ""

    with patch.dict(
        "os.environ",
        {
            "OBSIDIAN_SYNC_MODE": "local_rest",
            "OBSIDIAN_LOCAL_REST_URL": "http://127.0.0.1:27124",
            "OBSIDIAN_LOCAL_REST_TOKEN": "secret-token",
            "OBSIDIAN_DEFAULT_FOLDER": "COCO",
        },
        clear=False,
    ):
        with patch("app.integrations.obsidian.local_rest.requests.put", return_value=mock_resp) as put:
            r = client.post(
                "/api/integrations/obsidian/notes",
                json={
                    "title": "COCO-test",
                    "markdown": "# Note test",
                    "folder": "COCO/",
                    "source": "chat",
                },
            )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["mode"] == "local_rest"
    assert data["note_path"].startswith("COCO/")
    put.assert_called_once()
    assert put.call_args[0][0].endswith("/vault/COCO/COCO-test.md")


def test_failed_local_rest_falls_back_to_uri_handoff(client):
    with patch.dict(
        "os.environ",
        {
            "OBSIDIAN_SYNC_MODE": "local_rest",
            "OBSIDIAN_LOCAL_REST_URL": "http://127.0.0.1:27124",
            "OBSIDIAN_LOCAL_REST_TOKEN": "secret-token",
        },
        clear=False,
    ):
        import requests

        with patch(
            "app.integrations.obsidian.local_rest.requests.put",
            side_effect=requests.RequestException("connection refused"),
        ):
            r = client.post(
                "/api/integrations/obsidian/notes",
                json={"title": "COCO-fallback", "markdown": "# Fallback", "folder": "COCO"},
            )
    data = r.json()
    assert data["ok"] is True
    assert data["mode"] == "uri_handoff"
    assert data.get("fallback") is True
    assert data["uri"].startswith("obsidian://new")


def test_normal_salut_still_calls_chat_not_obsidian_intent():
    assert not _detect_obsidian_note_intent("Salut")
    send_fn = _html().split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "apiFetch('/chat'" in send_fn
    assert "console.info('[COCO:CHAT_POST_START]')" in send_fn
    obsidian_block = send_fn.split("ocDetectObsidianNoteIntent(text)")[0]
    assert "Salut" not in obsidian_block


def test_obsidian_intent_uses_connector_before_chat():
    html = _html()
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "await ocHandleObsidianChatIntent(text, 'note')" in send_fn
    assert "await ocHandleObsidianChatIntent(text, 'connect')" in send_fn
    assert "ocHandleObsidianChatIntent" in html
    assert "/api/integrations/obsidian/notes" in html
    assert "OC_OBSIDIAN_LOCAL_REST_SUCCESS_FR" in html
    assert _detect_obsidian_note_intent("Note ça dans Obsidian")
    assert _detect_obsidian_note_intent("Synchronise ça dans Obsidian")
    assert _detect_obsidian_note_intent("Enregistre cette conversation dans Obsidian")


def test_disabled_mode_returns_not_configured(client):
    with patch.dict("os.environ", {"OBSIDIAN_SYNC_MODE": "disabled"}, clear=False):
        r = client.post(
            "/api/integrations/obsidian/notes",
            json={"title": "x", "markdown": "# x"},
        )
    data = r.json()
    assert data["ok"] is False
    assert data["mode"] == "disabled"


def test_mobile_send_baseline_untouched():
    html = _html()
    assert "ocBindSendButtonTap(dom.send, ocHandleSendButtonClick)" in html
    mic_fn = html.split("function ocComposerActionIsMicMode")[1].split("function ocComposerHasSendPayload")[0]
    assert "return false" in mic_fn
