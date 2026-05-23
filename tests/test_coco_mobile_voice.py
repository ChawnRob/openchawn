"""COCO mobile voice dictation — draft-only, no auto-send."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_voice_state_flags_and_draft():
    html = _html()
    assert "isVoiceActive" in html
    assert "isVoiceManuallyStopped" in html
    assert "isRecognitionRestarting" in html
    assert "composerDraft" in html


def test_voice_no_auto_send_and_send_only_clear():
    html = _html()
    assert "window.ocVoicePrepareSend" in html
    assert "ocVoicePrepareSend()" in html
    assert "r.onresult = (ev)" in html
    assert "send();" not in html.split("r.onresult")[1].split("r.onerror")[0]


def test_voice_onend_preserves_draft_and_mobile_restart():
    html = _html()
    assert "ocFreezeDraftAsBase" in html
    assert "ocScheduleRecognitionRestart" in html
    assert "ocShouldRestartAfterEnd" in html
    assert "ocChatCleanMobileComposer()" in html.split("ocShouldRestartAfterEnd")[1][:500]


def test_mic_never_submits_from_callbacks():
    html = _html()
    block = html.split("function ocWireRecognitionInstance")[1].split("function ocStartVoiceRecognition")[0]
    assert "send(" not in block
