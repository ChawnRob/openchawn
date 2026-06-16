"""Composer microphone lifecycle — stop dictation on send, no auto-restart."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _speech_fn() -> str:
    return _html().split("(function ocInitSpeechInput()")[1].split("// ── Health check")[0]


def _send_fn() -> str:
    return _html().split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]


def _handler_fn() -> str:
    return _html().split("function ocHandleSendButtonClick")[1].split("dom.input.addEventListener('input'")[0]


def test_explicit_mic_states_defined():
    speech = _speech_fn()
    assert "const MIC_IDLE = 'micIdle'" in speech
    assert "const MIC_LISTENING = 'micListening'" in speech
    assert "const MIC_STOPPING = 'micStopping'" in speech
    assert "let micState = MIC_IDLE" in speech


def test_mic_tap_starts_listening_state():
    speech = _speech_fn()
    click_block = speech.split("btn.addEventListener('click'")[1].split("setMirrorForAvailability")[0]
    assert "micState = MIC_LISTENING" in click_block
    assert "rec.start()" in click_block
    assert "suppressSpeechSync = false" in click_block
    assert "speechStopReason = null" in click_block


def test_dictation_sync_requires_listening_state():
    speech = _speech_fn()
    sync_part = speech.split("function ocSyncSpeechToComposer")[1].split("function ocResetSpeechBuffers")[0]
    assert "micState !== MIC_LISTENING" in sync_part
    assert "suppressSpeechSync" in sync_part


def test_send_stops_recognition_and_clears_buffers():
    send_fn = _send_fn()
    before_chat = send_fn.split("console.info('[COCO:CHAT_POST_START]')")[0]
    assert "ocClearComposerDictationForSend()" in before_chat
    speech = _speech_fn()
    stop_fn = speech.split("function ocStopDictation")[1].split("ocClearComposerDictationForSend")[0]
    assert "speechStopReason = reason" in stop_fn
    assert "rec.abort()" in stop_fn
    assert "ocResetSpeechBuffers()" in speech


def test_onend_after_send_does_not_restart_recognition():
    speech = _speech_fn()
    onend = speech.split("r.onend = () => {")[1].split("};")[0]
    assert "reason === 'send'" in onend
    assert "suppressSpeechSync = true" in onend
    assert "rec.start()" not in onend
    assert "micState = MIC_IDLE" in onend


def test_send_clears_composer_and_syncs_idle_mic():
    html = _html()
    assert "function ocClearComposerInputAfterSend" in html
    clear_fn = html.split("function ocClearComposerInputAfterSend")[1].split("async function send")[0]
    assert "dom.input.value = ''" in clear_fn
    assert "ocSyncMobileComposerActionButton()" in clear_fn
    send_fn = _send_fn()
    assert "ocClearComposerInputAfterSend()" in send_fn


def test_finally_block_reasserts_mic_idle_after_response():
    send_fn = _send_fn()
    finally_block = send_fn.split("} finally {")[1]
    assert "ocClearComposerDictationForSend()" in finally_block
    assert "ocResetComposerSendEmergency()" in finally_block


def test_idle_mic_icon_when_empty_and_not_listening():
    sync_fn = _html().split("function ocSyncMobileComposerActionButton")[1].split(
        "function ocUpdateMobileComposerChrome"
    )[0]
    assert "ocComposerMicIsListening" in sync_fn
    assert "oc-composer-action-mic" in sync_fn
    assert "recording" in sync_fn


def test_second_dictation_requires_new_mic_tap():
    speech = _speech_fn()
    onend = speech.split("r.onend = () => {")[1].split("};")[0]
    click_block = speech.split("btn.addEventListener('click'")[1].split("setMirrorForAvailability")[0]
    assert "rec.start()" in click_block
    assert "rec.start()" not in onend
    assert "ocGetComposerMicState" in _html()
    assert "ocComposerMicIsListening" in _html()


def test_sending_disables_send_button():
    send_fn = _send_fn()
    assert "sending = true" in send_fn
    assert "dom.send.disabled = true" in send_fn
    handler = _handler_fn()
    assert handler.index("if (sending)") < handler.index("send()")
