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
    from app.auth import guest as guest_auth
    from app import middleware as mw

    guest_auth._sessions.clear()
    guest_auth._ip_sessions.clear()
    mw._buckets.clear()
    mw._last_chat_request_at.clear()
    mw._request_counts.clear()
    return TestClient(app)


def _guest_headers(client) -> dict[str, str]:
    r = client.post("/guest/session")
    assert r.status_code == 200
    return {"X-Guest-Session": r.json()["session_id"]}


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
                headers=_guest_headers(client),
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
                headers=_guest_headers(client),
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
            headers=_guest_headers(client),
        )
    data = r.json()
    assert data["ok"] is False
    assert data["mode"] == "disabled"


def test_mobile_send_baseline_untouched():
    html = _html()
    assert "ocBindSendButtonTap(dom.send, ocHandleSendButtonClick)" in html
    mic_fn = html.split("function ocComposerActionIsMicMode")[1].split("function ocComposerHasSendPayload")[0]
    assert "ocComposerHasSendPayload" in mic_fn
    handler = html.split("function ocHandleSendButtonClick")[1].split("dom.input.addEventListener('input'")[0]
    assert "ocComposerHasSendPayload()" in handler
    assert "console.info('[COCO:SEND_CALL]')" in handler


def test_obsidian_mobile_uri_handoff_contracts():
    html = _html()
    assert "OC_OBSIDIAN_URI_MAX_LENGTH" in html
    assert "1800" in html
    assert "[OBSIDIAN_URI_LENGTH]" in html
    assert "[OBSIDIAN_URI_VAULT]" in html
    assert "[OBSIDIAN_URI_MODE]" in html
    assert "ocBuildObsidianUriHandoffPack" in html
    assert "ocBuildObsidianCompactMarkdown" in html
    assert "uriNoVault" in html
    assert "open-obsidian-sync-no-vault" in html
    assert "Copier Markdown" in html
    assert "ouvrez Obsidian puis collez la note" in html
    assert "OC_OBSIDIAN_HANDOFF_PENDING_FR" in html
    assert "encodeURIComponent" in html.split("function ocBuildObsidianNewNoteUri")[1].split("function ocCopyObsidianMarkdown")[0]


def test_obsidian_mobile_pack_keeps_uri_under_limit():
    from app.integrations.obsidian.uri_handoff import build_obsidian_new_uri

    long_body = "# COCO test\n\n" + ("Ligne de contenu très longue. " * 400)
    uri = build_obsidian_new_uri(vault="OpenChawn", note_path="COCO/note", markdown=long_body)
    assert uri.startswith("obsidian://new?")
    uri_no_vault = build_obsidian_new_uri(vault="", note_path="COCO/note", markdown=long_body[:800])
    assert "vault=" not in uri_no_vault
    assert len(uri_no_vault) < len(uri)
