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


def _finalize_fn() -> str:
    return _html().split("function ocFinalizeComposerAfterChatTurn")[1].split("function ocClearComposerInputAfterSend")[0]


def _clear_fn() -> str:
    return _html().split("function ocClearComposerInputAfterSend")[1].split("async function send")[0]


def test_send_clears_composer_after_queueing_user_message():
    send_fn = _send_fn()
    before_add = send_fn.split("addMsg('user', userDisplay || chatMessage)")[0]
    assert "function ocHardResetComposerAfterSend" in _html()
    assert "ocHardResetComposerAfterSend()" in before_add
    assert "dom.input.value = ''" in _html().split("function ocHardResetComposerAfterSend")[1].split("function ocFinalizeComposerAfterChatTurn")[0]


def test_send_stops_dictation_before_chat_post():
    send_fn = _send_fn()
    before_chat = send_fn.split("console.info('[COCO:CHAT_POST_START]')")[0]
    assert "ocBumpComposerSendGeneration(text)" in before_chat
    assert "ocHardResetComposerAfterSend()" in before_chat
    assert "sending = true" in before_chat
    assert "dom.send.disabled = true" in before_chat


def test_dictation_buffers_suppressed_after_send_cleanup():
    speech = _speech_fn()
    assert "ocSpeechSessionIsStale(sessionGeneration)" in speech or "micState !== MIC_LISTENING" in speech
    assert "ocClearComposerDictationForSend = function" in speech
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
    assert "ocSyncMobileComposerActionButton()" in _html().split("function ocHardResetComposerAfterSend")[1].split("function ocFinalizeComposerAfterChatTurn")[0]


def test_double_tap_ignored_while_sending():
    handler = _handler_fn()
    send_fn = _send_fn()
    assert handler.index("if (sending)") < handler.index("send()")
    assert "ocNotifySendBlockedUi('sending_in_progress')" not in handler
    assert "sending_in_progress" in handler
    assert "if (sending)" in send_fn
    assert "dom.send.disabled = true" in send_fn


def test_last_sent_text_blocks_stale_draft_restore():
    html = _html()
    assert "let ocLastSentComposerText = ''" in html
    block_fn = html.split("function ocShouldBlockComposerDraftRestore")[1].split(
        "function ocGuardComposerInputAgainstStaleDraft"
    )[0]
    assert "draft === ocLastSentComposerText" in block_fn


def test_clear_composer_input_records_last_sent_text():
    clear_fn = _clear_fn()
    assert "ocBumpComposerSendGeneration(sentText)" in clear_fn
    assert "ocHardResetComposerAfterSend()" in clear_fn


def test_speech_sync_blocks_restoring_last_sent_text():
    speech = _speech_fn()
    sync_part = speech.split("function ocSyncSpeechToComposer")[1].split("function ocResetSpeechBuffers")[0]
    assert "ocShouldBlockComposerDraftRestore" in sync_part


def test_speech_onend_skips_ui_when_send_suppressed_sync():
    speech = _speech_fn()
    onend = speech.split("r.onend = () => {")[1].split("};")[0]
    assert "ocSpeechSessionIsStale(sessionGeneration)" in onend
    assert "micState = MIC_IDLE" in onend


def test_input_listener_guards_against_stale_draft():
    listener = _html().split("dom.input.addEventListener('input'")[1].split("dom.input.addEventListener('change'")[0]
    assert "ocLastSentComposerText" in listener
    assert "ocGuardComposerInputAgainstStaleDraft()" in listener


def test_composer_stays_empty_after_assistant_response():
    """Dictated text sends, composer clears, finally block keeps it empty after /chat."""
    send_fn = _send_fn()
    assert "ocHardResetComposerAfterSend()" in send_fn
    finally_block = send_fn.split("} finally {")[1]
    assert "ocFinalizeComposerAfterChatTurn()" in finally_block
    assert finally_block.index("ocFinalizeComposerAfterChatTurn()") < finally_block.index(
        "ocResetComposerSendEmergency()"
    )
    finalize_fn = _finalize_fn()
    assert "ocHardResetComposerAfterSend()" in finalize_fn


def test_second_tap_after_response_cannot_resend_stale_text():
    """Empty composer after finalize means send() exits on empty_payload."""
    send_fn = _send_fn()
    assert "const text = dom.input.value.trim();" in send_fn
    assert "if (!text && !hasAttachment)" in send_fn
    assert "empty_payload" in send_fn
    handler = _handler_fn()
    assert "if (sending)" in handler
