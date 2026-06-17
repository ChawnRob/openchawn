"""Regression tests for COCO mobile composer, language, Obsidian, markdown UI."""

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
        r"\b(peux|peut)\s+tu\s+me\s+synchronis\w*\s+obsidian\b",
        r"\b(peux|peut)\s+tu\s+me\s+connect\w*\s+a\s+obsidian\b",
        r"\bsynchronis\w*\s+(a|avec|to)\s+obsidian\b",
        r"\bsynchronis\w*\s+obsidian\b",
        r"\bsynchronis\w*\s+avec\s+obsidian\b",
        r"\bconnecte[- ]?moi\s+a\s+obsidian\b",
        r"\bouvr\w*\s+obsidian\b",
        r"\bme\s+connecter\s+a\s+obsidian\b",
    ]
    return any(re.search(p, t) for p in phrase_patterns)


def _detect_language_complaint_intent(text: str) -> bool:
    t = _normalize_obsidian_intent_text(text)
    return bool(
        re.search(r"\b(pourquoi|why)\b", t)
        and (
            re.search(r"\b(repond|reply|replies|parle|speak|ecri)\w*\b", t)
            or re.search(r"\b(en anglais|in english)\b", t)
        )
        and re.search(r"\b(anglais|english)\b", t)
    )


OC_OBSIDIAN_DENIAL_EN = (
    "I cannot trigger Obsidian",
    "backend integration is not active",
    "use the button manually",
    "no active connector",
)


def test_mobile_composer_dual_control_layout():
    html = _html()
    mobile = html.split("/* V11.6.3 mobile composer vertical alignment fix */")[1].split(
        "@media (max-width: 896px)"
    )[0]
    composer = mobile.split("/* Composer final: [ champ texte ] [ micro|envoyer ] */")[1]
    assert "textarea" in composer
    assert ".send-btn" in composer
    assert 'id="cocoComposerAttachSlot"' in html
    assert "📎 Photo/Fichier" in html
    mic_hide = mobile.split("html.ux-chat-clean .clean-input-shell .input-wrapper #btnSpeech")[1].split(
        "/* Composer final"
    )[0]
    assert "display: none !important" in mic_hide


def test_mobile_composer_action_toggle_contract():
    html = _html()
    assert "oc-composer-action-send" in html
    assert "function ocSyncMobileComposerActionButton" in html
    toggle_fn = html.split("function ocSyncMobileComposerActionButton")[1].split(
        "function ocUpdateMobileComposerChrome"
    )[0]
    assert "oc-composer-action-send" in toggle_fn
    assert "oc-composer-action-mic" in toggle_fn
    assert "Micro dictée" in toggle_fn
    assert "Envoyer à OpenChawn" in toggle_fn
    click_block = html.split("function ocHandleSendButtonClick")[1].split("dom.input.addEventListener('input'")[0]
    assert "ocComposerHasSendPayload()" in click_block
    assert "ocComposerActionIsMicMode()" in click_block
    assert "dom.btnSpeech?.click" in click_block
    assert "ocBindSendButtonTap(dom.send, ocHandleSendButtonClick)" in _html()


def test_mobile_composer_mic_send_chatgpt_toggle():
    html = _html()
    mic_mode_fn = html.split("function ocComposerActionIsMicMode")[1].split("function ocComposerHasSendPayload")[0]
    assert "ocComposerHasSendPayload" in mic_mode_fn
    assert "return false" not in mic_mode_fn.replace(" ", "")
    sync_fn = html.split("function ocSyncMobileComposerActionButton")[1].split("function ocUpdateMobileComposerChrome")[0]
    assert "oc-composer-action-mic" in sync_fn
    assert "Micro dictée" in sync_fn
    assert "Envoyer à OpenChawn" in sync_fn


def test_attach_chip_in_toolbar_row():
    html = _html()
    assert 'id="cocoComposerAttachSlot"' in html
    assert "coco-file-intake-chip" in html
    assert "📎 Photo/Fichier" in html
    mobile = html.split("html.ux-chat-clean .clean-input-shell .input-wrapper #btnFileIntake {")[1].split(
        "html.ux-chat-clean .coco-mobile-mic-mount"
    )[0]
    assert "display: none !important" in mobile


def test_night_mode_attach_and_action_mic_selectors():
    html = _html()
    for sel in (
        "html.oc-theme-night #btnFileIntake",
        "body.oc-night-mode #btnFileIntake",
        "html[data-theme=\"night\"] #btnFileIntake",
        "body[data-theme=\"night\"] #sendBtn.oc-composer-action-mic",
        "html.oc-theme-night #sendBtn.oc-composer-action-mic",
    ):
        assert sel in html
    assert "rgba(3, 18, 31, 0.96) !important" in html
    assert "rgba(255,255,255,0.98)" not in html.split("#btnFileIntake,")[1].split("cursor: pointer")[0]


def test_language_complaint_short_circuit_and_backend_meta():
    from app.core.language_policy import (
        build_language_instruction,
        detect_explicit_language_request,
        derive_response_language_trace,
    )

    phrase = "Pourquoi me répond tu en anglais ?"
    assert _detect_language_complaint_intent(phrase)
    html = _html()
    assert "ocDetectLanguageComplaintIntent" in html
    assert "ocAddLanguageComplaintAssistantMessage" in html
    assert "ocSanitizeChatOutboundMessage" in html
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocDetectLanguageComplaintIntent(text)" in send_fn
    assert "ocSanitizeChatOutboundMessage(chatMessage)" in send_fn

    assert detect_explicit_language_request(phrase) is None
    trace = derive_response_language_trace(phrase)
    assert trace["response_language_mode"] == "auto"
    assert trace["final_language"] == "fr"
    instr = build_language_instruction(phrase).lower()
    assert "explicitly requested english" not in instr
    assert "output language: english" not in instr
    assert "français" in instr


def test_obsidian_connect_phrases_short_circuit_list():
    phrases = [
        "Peux tu me synchroniser à Obsidian ?",
        "Peux tu me synchroniser Obsidian",
        "Peux tu me connecter à Obsidian",
        "Connecte moi à Obsidian",
        "Ouvre Obsidian",
        "Synchronise avec Obsidian",
    ]
    for phrase in phrases:
        assert _detect_obsidian_connect_intent(phrase), phrase

    reply = (
        _html()
        .split("var OC_OBSIDIAN_URI_CONNECT_FR =")[1]
        .split(";")[0]
        .strip()
        .strip("'")
        .encode("utf-8")
        .decode("unicode_escape")
        .replace("\\u2019", "'")
    )
    assert "Sync Obsidian" in reply
    assert "Markdown" in reply
    assert "votre appareil" in reply
    for denial in OC_OBSIDIAN_DENIAL_EN:
        assert denial not in reply

    send_fn = _html().split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "await ocHandleObsidianChatIntent(text, 'connect')" in send_fn
    connect_fn = _html().split("function ocRenderObsidianUriAssistantMessage")[1].split(
        "function ocAddObsidianConnectAssistantMessage"
    )[0]
    assert "ocBuildObsidianSyncButton(handoff.uri" in connect_fn
    sync_btn_fn = _html().split("function ocBuildObsidianSyncButton")[1].split(
        "function ocObsidianNoteTitlePath"
    )[0]
    assert "data-obsidian-uri" in sync_btn_fn
    assert "obsidian://new" in sync_btn_fn or "obsidian://new" in _html()


def test_assistant_markdown_bold_rendered():
    html = _html()
    assert "function ocFormatAssistantMessageHtml" in html
    add_fn = html.split("function addMsg(role, text, meta, opts)")[1].split("let ocImagePipelineStatusEl")[0]
    assert "ocFormatAssistantMessageHtml(text)" in add_fn
    assert "<strong>$1</strong>" in html


def test_mobile_send_button_sends_plain_text_after_pr20():
    html = _html()
    handler = html.split("function ocHandleSendButtonClick")[1].split(
        "dom.input.addEventListener('input'"
    )[0]
    assert "ocBindSendButtonTap(dom.send, ocHandleSendButtonClick)" in html
    assert "console.info('[COCO:SEND_TAP]'" in handler
    assert "console.info('[COCO:SEND_CALL]')" in handler
    assert "send()" in handler
    assert "ocComposerHasSendPayload()" in handler
    assert not _detect_obsidian_connect_intent("Salut")


def test_mobile_composer_detects_coarse_pointer_tablets():
    html = _html()
    fn = html.split("function ocChatCleanMobileComposer")[1].split("function ocComposerInputHasSendAction")[0]
    assert "pointer: coarse" in fn
    assert "max-width: 1024px" in fn


def test_obsidian_intercept_does_not_block_normal_send():
    phrase = "Salut"
    assert not _detect_obsidian_connect_intent(phrase)

    html = _html()
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    obsidian_block = send_fn.split("ocDetectObsidianConnectIntent(text)")[1].split("sending = true")[0]
    assert "await ocHandleObsidianChatIntent(text, 'connect')" in obsidian_block
    assert "return" in obsidian_block
    assert "apiFetch('/chat'" in send_fn.split("ocDetectObsidianConnectIntent(text)")[1]
