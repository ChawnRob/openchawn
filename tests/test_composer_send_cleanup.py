"""Composer send cleanup after dictation — no stale text or duplicate sends."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _send_fn() -> str:
    return _html().split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]


def _handler_fn() -> str:
    return _html().split("function ocHandleSendButtonClick")[1].split("dom.input.addEventListener('input'")[0]


def _speech_fn() -> str:
    return _html().split("(function ocInitSpeechInput()")[1].split("// ── Health check")[0]


def test_send_clears_composer_after_queueing_user_message():
    send_fn = _send_fn()
    before_add = send_fn.split("addMsg('user', userDisplay || chatMessage)")[0]
    assert "function ocClearComposerInputAfterSend" in _html()
    assert "ocClearComposerInputAfterSend()" in before_add
    assert "dom.input.value = ''" in _html().split("function ocClearComposerInputAfterSend")[1].split("async function send")[0]


def test_send_stops_dictation_before_chat_post():
    send_fn = _send_fn()
    before_chat = send_fn.split("console.info('[COCO:CHAT_POST_START]')")[0]
    assert "ocClearComposerDictationForSend()" in before_chat
    assert "sending = true" in before_chat
    assert "dom.send.disabled = true" in before_chat


def test_dictation_buffers_suppressed_after_send_cleanup():
    speech = _speech_fn()
    assert "suppressSpeechSync" in speech
    assert "ocClearComposerDictationForSend = function" in speech
    assert "if (suppressSpeechSync) return" in speech
    assert "rec.abort()" in speech


def test_successful_send_resets_mic_when_no_attachment():
    send_fn = _send_fn()
    finally_block = send_fn.split("} finally {")[1]
    assert "ocResetComposerSendEmergency()" in finally_block
    assert "sending = false" in finally_block
    sync_fn = _html().split("function ocSyncMobileComposerActionButton")[1].split(
        "function ocUpdateMobileComposerChrome"
    )[0]
    assert "oc-composer-action-mic" in sync_fn
    clear_fn = _html().split("function ocClearComposerInputAfterSend")[1].split("async function send")[0]
    assert "ocSyncMobileComposerActionButton()" in clear_fn


def test_double_tap_ignored_while_sending():
    handler = _handler_fn()
    send_fn = _send_fn()
    assert handler.index("if (sending)") < handler.index("send()")
    assert "ocNotifySendBlockedUi('sending_in_progress')" not in handler
    assert "sending_in_progress" in handler
    assert "if (sending)" in send_fn
    assert "dom.send.disabled = true" in send_fn
