"""Composer microphone lifecycle — stop dictation on send, empty composer after send."""

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


def _hard_reset_fn() -> str:
    return _html().split("function ocHardResetComposerAfterSend")[1].split("async function send")[0]


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
    assert "const sessionGeneration = composerSendGeneration" in click_block


def test_dictation_sync_requires_listening_state_and_generation():
    speech = _speech_fn()
    sync_part = speech.split("function ocSyncSpeechToComposer")[1].split("function ocResetSpeechBuffers")[0]
    assert "ocSpeechSessionIsStale(sessionGeneration)" in sync_part
    assert "micState !== MIC_LISTENING" in sync_part
    assert "suppressSpeechSync" in sync_part
    assert "sending" in sync_part


def test_send_stops_recognition_and_clears_buffers():
    send_fn = _send_fn()
    before_chat = send_fn.split("console.info('[COCO:CHAT_POST_START]')")[0]
    assert "ocBumpComposerSendGeneration(text)" in before_chat
    assert "ocHardResetComposerAfterSend()" in before_chat
    speech = _speech_fn()
    assert "rec.abort()" in speech
    assert "ocResetComposerSpeechBuffers" in _html()


def test_onend_after_send_does_not_restart_recognition():
    speech = _speech_fn()
    onend = speech.split("r.onend = () => {")[1].split("};")[0]
    assert "ocSpeechSessionIsStale(sessionGeneration)" in onend
    assert "rec.start()" not in onend
    assert "micState = MIC_IDLE" in onend


def test_hard_reset_clears_textarea_and_speech_buffers():
    reset_fn = _hard_reset_fn()
    assert "ocClearComposerDictationForSend" in reset_fn
    assert "ocResetComposerSpeechBuffers" in reset_fn
    assert "dom.input.value = ''" in reset_fn
    assert "dom.input.textContent = ''" in reset_fn
    assert "dispatchEvent(new Event('input'" in reset_fn
    assert "ocSyncMobileComposerActionButton()" in reset_fn
    assert "oc_composer_draft" in reset_fn


def test_send_calls_hard_reset_at_three_points():
    send_fn = _send_fn()
    after_capture = send_fn.split("let chatMessage = text")[1].split("addMsg('user'")[0]
    assert "ocHardResetComposerAfterSend()" in after_capture
    post_start_region = send_fn.split("console.info('[COCO:CHAT_POST_START]')")[0]
    assert post_start_region.count("ocHardResetComposerAfterSend()") >= 1
    after_post_start = send_fn.split("console.info('[COCO:CHAT_POST_START]')")[1].split("} catch")[0]
    assert "ocHardResetComposerAfterSend()" in after_post_start
    finally_block = send_fn.split("} finally {")[1]
    assert "ocFinalizeComposerAfterChatTurn()" in finally_block


def test_composer_send_generation_increments_on_send():
    html = _html()
    assert "let composerSendGeneration = 0" in html
    assert "function ocBumpComposerSendGeneration" in html
    send_fn = _send_fn()
    assert "ocBumpComposerSendGeneration(text)" in send_fn


def test_stale_dictated_text_blocked_after_send():
    html = _html()
    assert "let ocLastSentComposerText = ''" in html
    assert "function ocShouldBlockComposerDraftRestore" in html
    assert "function ocGuardComposerInputAgainstStaleDraft" in html
    guard_fn = html.split("function ocGuardComposerInputAgainstStaleDraft")[1].split("function ocBumpComposerSendGeneration")[0]
    assert "sending" in guard_fn
    assert "draft === ocLastSentComposerText" in html.split("function ocShouldBlockComposerDraftRestore")[1].split("function ocGuardComposerInputAgainstStaleDraft")[0]
    listener = html.split("dom.input.addEventListener('input'")[1].split("dom.input.addEventListener('change'")[0]
    assert "ocGuardComposerInputAgainstStaleDraft()" in listener


def test_dictated_bonjour_send_leaves_empty_composer_after_response():
    """Dictate Bonjour → send → finally hard reset → idle mic, no stale resend."""
    send_fn = _send_fn()
    assert "ocBumpComposerSendGeneration(text)" in send_fn
    finally_block = send_fn.split("} finally {")[1]
    assert "ocFinalizeComposerAfterChatTurn()" in finally_block
    assert "ocResetComposerSendEmergency()" in finally_block
    assert "const text = dom.input.value.trim();" in send_fn
    assert "if (!text && !hasAttachment)" in send_fn
    sync_fn = _html().split("function ocSyncMobileComposerActionButton")[1].split("function ocUpdateMobileComposerChrome")[0]
    assert "oc-composer-action-mic" in sync_fn
    assert "ocComposerMicIsListening" in sync_fn


def test_idle_mic_icon_when_empty_and_not_listening():
    sync_fn = _html().split("function ocSyncMobileComposerActionButton")[1].split(
        "function ocUpdateMobileComposerChrome"
    )[0]
    assert "ocComposerMicIsListening" in sync_fn
    assert "oc-composer-action-mic" in sync_fn


def test_second_dictation_requires_new_mic_tap():
    speech = _speech_fn()
    onend = speech.split("r.onend = () => {")[1].split("};")[0]
    click_block = speech.split("btn.addEventListener('click'")[1].split("setMirrorForAvailability")[0]
    assert "rec.start()" in click_block
    assert "rec.start()" not in onend


def test_sending_disables_send_button():
    send_fn = _send_fn()
    assert "sending = true" in send_fn
    assert "dom.send.disabled = true" in send_fn
    handler = _handler_fn()
    assert handler.index("if (sending)") < handler.index("send()")
