"""Mobile composer send baseline — reliable #sendBtn hotfix regression tests."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _normalize_obsidian_intent_text(text: str) -> str:
    t = str(text or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\u2019", "'").replace("'", "'")
    t = re.sub(r"\bes\s+ce\b", "est-ce", t)
    t = re.sub(r"\best\s+ce\b", "est-ce", t)
    return re.sub(r"\s+", " ", t).strip()


def _detect_obsidian_connect_intent(text: str) -> bool:
    t = _normalize_obsidian_intent_text(text)
    if not t or not re.search(r"\bobsidian\b", t):
        return False
    phrase_patterns = [
        r"\b(peux|peut)\s+tu\s+me\s+synchronis\w*\s+(a|avec|to)\s+obsidian\b",
        r"\bsynchronis\w*\s+(a|avec|to)\s+obsidian\b",
        r"\bsynchronis\w*\s+obsidian\b",
    ]
    return any(re.search(p, t) for p in phrase_patterns)


def _handler_fn() -> str:
    return _html().split("function ocHandleSendButtonClick")[1].split("dom.input.addEventListener('input'")[0]


def _bind_fn() -> str:
    return _html().split("function ocBindSendButtonTap")[1].split("function ocHandleSendButtonClick")[0]


def _send_fn() -> str:
    return _html().split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]


def test_mobile_salut_calls_send_not_speech():
    html = _html()
    handler = _handler_fn()
    assert "function ocHandleSendButtonClick" in html
    assert "ocBindSendButtonTap(dom.send, ocHandleSendButtonClick)" in html
    assert "console.info('[COCO:SEND_CALL]')" in handler
    assert "send()" in handler
    assert "dom.btnSpeech?.click" not in handler
    assert "ocComposerHasSendPayload()" in handler


def test_send_button_has_click_pointerup_touchend():
    bind = _bind_fn()
    assert "addEventListener('click', run)" in bind
    assert "addEventListener('pointerup'" in bind
    assert "addEventListener('touchend'" in bind


def test_send_calls_chat_for_normal_text():
    send_fn = _send_fn()
    assert "console.info('[COCO:CHAT_POST_START]')" in send_fn
    assert "apiFetch('/chat'" in send_fn
    assert "console.info('[COCO:CHAT_POST_DONE]')" in send_fn


def test_obsidian_intercept_does_not_run_for_salut():
    assert not _detect_obsidian_connect_intent("Salut")
    send_fn = _send_fn()
    before_chat = send_fn.split("console.info('[COCO:CHAT_POST_START]')")[0]
    assert "ocDetectObsidianConnectIntent(text)" in before_chat
    assert "ocAddObsidianConnectAssistantMessage(text)" in before_chat


def test_empty_text_shows_blocked_ui_not_chat():
    handler = _handler_fn()
    send_fn = _send_fn()
    assert "ocNotifySendBlockedUi('empty_input')" in handler
    assert "ocNotifySendBlockedUi('empty_payload')" in send_fn
    assert "Envoi bloqué côté interface. Rechargez la page." in _html()


def test_stale_mic_class_cannot_prevent_text_send():
    html = _html()
    sync_fn = html.split("function ocSyncMobileComposerActionButton")[1].split(
        "function ocUpdateMobileComposerChrome"
    )[0]
    handler = _handler_fn()
    assert "oc-composer-action-mic" in sync_fn
    assert "remove('oc-composer-action-mic'" in sync_fn
    assert "ocComposerHasSendPayload()" in handler
    assert "oc-composer-action-mic" not in handler or "dom.btnSpeech" not in handler


def test_disabled_and_sending_cleared_after_failed_request():
    send_fn = _send_fn()
    assert "TRANSMISSION FAILED" in send_fn
    assert send_fn.count("ocResetComposerSendEmergency()") >= 2
    assert "sending = false" in _html().split("function ocResetComposerSendEmergency")[1].split(
        "function ocNotifySendBlockedUi"
    )[0]


def test_emergency_reset_on_page_load():
    html = _html()
    assert "function ocResetComposerSendEmergency" in html
    reset_fn = html.split("function ocResetComposerSendEmergency")[1].split("function ocNotifySendBlockedUi")[0]
    assert "sending = false" in reset_fn
    assert "dom.send.disabled = false" in reset_fn
    assert "ocResetComposerSendEmergency();" in html.split("ocBindSendButtonTap(dom.send")[0]
    assert html.count("ocResetComposerSendEmergency();") >= 2


def test_mic_toggle_disabled_baseline():
    html = _html()
    mic_mode_fn = html.split("function ocComposerActionIsMicMode")[1].split(
        "function ocComposerHasSendPayload"
    )[0]
    assert "return false" in mic_mode_fn
