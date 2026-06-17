"""COCO Study/Career Knowledge Organizer — intent, notes, and UI contract."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from app.core.knowledge_organizer import (
    DENIAL_PHRASES,
    KNOWLEDGE_ORGANIZER_MARKER,
    NOTE_TYPES,
    build_knowledge_organizer_context,
    build_knowledge_organizer_note,
    classify_note_type,
    detect_knowledge_organizer_intent,
    resolve_suggested_destination,
)

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    t = str(text or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\u2019", "'").replace("'", "'")
    t = re.sub(r"\bes\s+ce\b", "est-ce", t)
    t = re.sub(r"\best\s+ce\b", "est-ce", t)
    return re.sub(r"\s+", " ", t).strip()


def _detect_knowledge_organizer_intent(text: str) -> bool:
    """Mirror of ocDetectKnowledgeOrganizerIntent in static/index.html."""
    t = _normalize(text)
    if not t:
        return False
    patterns = [
        r"\b(range|organis\w*|structure)\w*\s+(ce\s+)?cours\b",
        r"\bcours\b.*\b(obsidian|affine)\b",
        r"\b(obsidian|affine)\b.*\bcours\b",
        r"\bfiche\s+de\s+revision\b",
        r"\bfiche\s+de\s+revis\w+\b",
        r"\bfais[- ]?moi\s+une\s+fiche\b",
        r"\bnote\s+ma\s+progression\b",
        r"\b(progress(?:ion)?|suivi)\b.*\b(anglais|matiere|matière|obsidian|affine)\b",
        r"\b(prepare|prépare|preparer)\w*\s+une\s+note\s+(carriere|carrière|orientation)\b",
        r"\bnote\s+(carriere|carrière|orientation)\b",
        r"\b(mets|met)\w*\s+(cette\s+)?idee\s+(dans\s+)?affine\b",
        r"\b(mets|met)\w*\s+(cette\s+)?idée\s+(dans\s+)?affine\b",
        r"\b(capture|captur)\w*\s+(cette\s+)?idee\b",
        r"\bprojet\b.*\b(note|obsidian|affine)\b",
        r"\b(revision|revis\w+|orientation|carriere|carrière)\b.*\b(obsidian|affine)\b",
    ]
    return any(re.search(p, t) for p in patterns)


def _knowledge_reply_from_html() -> str:
    reply = _html().split("var OC_KNOWLEDGE_ORGANIZER_FR =")[1].split(";")[0]
    reply = reply.strip().strip("'")
    return reply.encode("utf-8").decode("unicode_escape").replace("\\u2019", "'")


def _send_fn() -> str:
    return _html().split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]


def _assert_no_denial(text: str) -> None:
    low = text.lower()
    for phrase in DENIAL_PHRASES:
        assert phrase not in low, f"Unexpected denial phrase: {phrase!r} in {text!r}"


REGRESSION_CASES = [
    (
        "Range ce cours dans Obsidian",
        "course",
        "Obsidian",
        "Envoyer vers Obsidian",
    ),
    (
        "Fais-moi une fiche de révision en maths",
        "revision",
        "Obsidian ou AFFiNE",
        "Copier la note",
    ),
    (
        "Mets cette idée dans AFFiNE",
        "idea",
        "AFFiNE",
        "Envoyer vers AFFiNE",
    ),
    (
        "Note ma progression en anglais",
        "progress",
        "Obsidian ou AFFiNE",
        "Copier la note",
    ),
    (
        "Prépare une note carrière",
        "career",
        "Obsidian ou AFFiNE",
        "Copier la note",
    ),
]


@pytest.mark.parametrize(
    "phrase,expected_type,expected_dest,_button_hint",
    REGRESSION_CASES,
    ids=[c[0][:32] for c in REGRESSION_CASES],
)
def test_knowledge_organizer_regression_phrases(
    phrase: str, expected_type: str, expected_dest: str, _button_hint: str
):
    assert detect_knowledge_organizer_intent(phrase)
    assert _detect_knowledge_organizer_intent(phrase)
    assert classify_note_type(phrase) == expected_type
    assert resolve_suggested_destination(phrase) == expected_dest

    note = build_knowledge_organizer_note(phrase)
    assert note["note_type"] == expected_type
    assert note["suggested_destination"] == expected_dest
    assert note["title"].startswith("COCO-")
    assert "## Métadonnées" in note["markdown"]
    assert "**Destination suggérée:**" in note["markdown"]
    assert expected_dest in note["markdown"]
    assert "## Destination" in note["markdown"]
    assert len(note["sections"]) >= 3
    for heading in note["sections"]:
        assert f"## {heading}" in note["markdown"]

    reply = _knowledge_reply_from_html().replace("{dest}", expected_dest)
    _assert_no_denial(reply)
    assert "note Markdown" in reply.lower() or "markdown" in reply.lower()
    assert "bouton" in reply.lower()


def test_all_note_types_supported():
    assert set(NOTE_TYPES) == {
        "course",
        "revision",
        "project",
        "progress",
        "career",
        "idea",
    }


def test_build_knowledge_organizer_context_capabilities():
    ctx = build_knowledge_organizer_context()
    assert KNOWLEDGE_ORGANIZER_MARKER in ctx
    assert "structured Markdown notes" in ctx
    assert "Obsidian" in ctx
    assert "AFFiNE" in ctx
    assert "CANNOT confirm final vault persistence" in ctx
    assert "Envoyer vers Obsidian" in ctx
    assert "Copier la note" in ctx
    for phrase in (
        "Range ce cours dans Obsidian",
        "Fais-moi une fiche de révision en maths",
        "Mets cette idée dans AFFiNE",
        "Note ma progression en anglais",
        "Prépare une note carrière",
    ):
        assert phrase in ctx


def test_coco_system_prompt_includes_knowledge_organizer():
    from app.api.chat import build_openchawn_base_system_prompt

    prompt = build_openchawn_base_system_prompt()
    assert KNOWLEDGE_ORGANIZER_MARKER in prompt
    assert "Knowledge Organizer" in prompt
    assert "structured Markdown notes" in prompt


def test_send_intercepts_knowledge_organizer_before_chat():
    send_fn = _send_fn()
    before_chat = send_fn.split("console.info('[COCO:CHAT_POST_START]')")[0]
    ko_pos = before_chat.find("ocDetectKnowledgeOrganizerIntent(text)")
    obs_note_pos = before_chat.find("ocDetectObsidianNoteIntent(text)")
    assert ko_pos >= 0
    assert obs_note_pos >= 0
    assert ko_pos < obs_note_pos
    assert "await ocHandleKnowledgeOrganizerIntent(text)" in before_chat


def test_ui_knowledge_organizer_buttons_and_handlers():
    html = _html()
    assert "function ocDetectKnowledgeOrganizerIntent" in html
    assert "function ocBuildKnowledgeOrganizerNote" in html
    assert "function ocHandleKnowledgeOrganizerIntent" in html
    assert "function ocRenderKnowledgeOrganizerAssistant" in html
    assert "Envoyer vers Obsidian" in html
    assert "Envoyer vers AFFiNE" in html
    assert "Copier la note" in html
    assert 'data-coco-knowledge-action="copy-knowledge-note"' in html
    assert 'data-coco-knowledge-action="open-affine-second-brain"' in html
    assert 'data-coco-knowledge-action="open-obsidian-sync"' in html

    reply = _knowledge_reply_from_html()
    _assert_no_denial(reply)
    assert "{dest}" in reply


def test_knowledge_organizer_preserves_mobile_send_baseline():
    html = _html()
    assert "ocBindSendButtonTap(dom.send, ocHandleSendButtonClick)" in html
    mic_mode_fn = html.split("function ocComposerActionIsMicMode")[1].split(
        "function ocComposerHasSendPayload"
    )[0]
    assert "ocComposerHasSendPayload" in mic_mode_fn
    normalized = mic_mode_fn.replace(" ", "").replace("\n", "")
    assert "return!ocComposerHasSendPayload()" in normalized


def test_knowledge_organizer_obsidian_api_handoff():
    handler = _html().split("async function ocHandleKnowledgeOrganizerIntent")[1].split(
        "function ocDetectObsidianNoteIntent"
    )[0]
    assert "/api/integrations/obsidian/notes" in handler
    assert "source: 'knowledge_organizer'" in handler
    assert "local_rest" in handler
    assert "ocBuildObsidianNewNoteUri" in handler
    assert "noté dans Obsidian" in handler
    assert "d.note_path" in handler
