"""Composer mic/send toggle and Photo/Fichier toolbar row layout."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_empty_composer_defaults_to_microphone_button():
    html = _html()
    send_tag = html.split('id="sendBtn"')[0].split("<button")[-1] + 'id="sendBtn"'
    assert "oc-composer-action-mic" in send_tag
    sync_fn = html.split("function ocSyncMobileComposerActionButton")[1].split(
        "function ocUpdateMobileComposerChrome"
    )[0]
    assert "oc-composer-action-mic" in sync_fn
    assert "Micro dictée" in sync_fn
    mic_fn = html.split("function ocComposerActionIsMicMode")[1].split("function ocComposerHasSendPayload")[0]
    assert "ocComposerHasSendPayload" in mic_fn


def test_typed_text_switches_to_send_button():
    html = _html()
    handler = html.split("function ocHandleSendButtonClick")[1].split("dom.input.addEventListener('input'")[0]
    sync_fn = html.split("function ocSyncMobileComposerActionButton")[1].split(
        "function ocUpdateMobileComposerChrome"
    )[0]
    assert "ocComposerHasSendPayload()" in handler
    assert "oc-composer-action-send" in sync_fn
    assert "Envoyer à OpenChawn" in sync_fn
    assert "dom.input.addEventListener('input'" in html
    assert "ocSyncMobileComposerActionButton()" in html.split("dom.input.addEventListener('input'")[1][:400]


def test_photo_fichier_chip_in_toolbar_not_composer():
    html = _html()
    assert 'id="ocComposerMobileToolbar"' in html
    assert 'id="cocoComposerAttachSlot"' in html
    assert "📎 Photo/Fichier" in html
    mobile = html.split("/* Composer final: [ champ texte ] [ micro|envoyer ] */")[1].split(
        "html.ux-chat-clean .coco-mobile-mic-mount"
    )[0]
    assert "input-wrapper #btnFileIntake" in mobile
    assert "display: none !important" in mobile
    base_toolbar = html.split("html.ux-chat-clean .oc-composer-mobile-toolbar {")[1].split("}")[0]
    assert "display: flex" in base_toolbar
    assert "max-height" not in base_toolbar
    assert "overflow: hidden" not in base_toolbar


def test_attach_handlers_remain_bound():
    html = _html()
    setup = html.split("(function ocFileIntakeUiSetup()")[1].split("})();")[0]
    assert "ocBindFileIntakeTap(btnAttach" in setup
    assert "ocPickFileIntakeSource('camera')" in setup
    assert "ocPickFileIntakeSource('gallery')" in setup
    assert "ocPickFileIntakeSource('file')" in setup
    assert 'id="fileIntakeInputCamera"' in html
    assert 'id="fileIntakeInputGallery"' in html
    assert 'id="fileIntakeInputFile"' in html


def test_pending_attachment_keeps_send_visible():
    html = _html()
    payload_fn = html.split("function ocComposerHasSendPayload")[1].split("function ocResetComposerSendEmergency")[0]
    assert "ocHasPendingImageAttachment" in payload_fn
    chip_fn = html.split("function ocShowComposerAttachmentChip")[1].split("function ocHasPendingImageAttachment")[0]
    assert "ocSyncMobileComposerActionButton()" in chip_fn
