"""Obsidian optional sync — status API and UI contract."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _obsidian_block() -> str:
    html = _html()
    return html.split("var ocObsidianSyncConfig")[1].split("document.getElementById('cocoPromptChips')")[0]


def _normalize_obsidian_intent_text(text: str) -> str:
    t = str(text or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("\u2019", "'").replace("'", "'")
    t = re.sub(r"\bes\s+ce\b", "est-ce", t)
    t = re.sub(r"\best\s+ce\b", "est-ce", t)
    return re.sub(r"\s+", " ", t).strip()


def _detect_obsidian_note_intent(text: str) -> bool:
    """Mirror of ocDetectObsidianNoteIntent in static/index.html."""
    t = _normalize_obsidian_intent_text(text)
    if not t or not re.search(r"\bobsidian\b", t):
        return False
    if re.search(r"\baffine\b", t) and not re.search(
        r"\bobsidian\b", re.sub(r"\baffine\b", "", t)
    ):
        return False
    note_patterns = [
        r"\bnote\s+(ca\s+)?dans\s+obsidian\b",
        r"\bajout\w*\s+(ca\s+)?dans\s+obsidian\b",
        r"\bsauvegard\w*\s+dans\s+obsidian\b",
        r"\becri\w*\s+(ca\s+)?dans\s+obsidian\b",
        r"\bcree\w*\s+une\s+note\s+obsidian\b",
        r"\bmet\w*\s+(ca\s+)?dans\s+obsidian\b",
        r"\benregistr\w*\s+dans\s+obsidian\b",
        r"\btravaill\w*\s+dans\s+obsidian\b",
    ]
    return any(re.search(p, t) for p in note_patterns)


def _detect_obsidian_connect_intent(text: str) -> bool:
    """Mirror of ocDetectObsidianConnectIntent in static/index.html."""
    t = _normalize_obsidian_intent_text(text)
    if not t or not re.search(r"\bobsidian\b", t):
        return False
    if re.search(r"\baffine\b", t) and not re.search(
        r"\bobsidian\b", re.sub(r"\baffine\b", "", t)
    ):
        return False
    phrase_patterns = [
        r"\bsync\s+(avec|to)\s+obsidian\b",
        r"\bsync\s+obsidian\b",
        r"\bfaire\s+le\s+sync\s+avec\s+obsidian\b",
        r"\bfaire\s+la\s+sync\s+avec\s+obsidian\b",
        r"\b(peux|peut)\s+tu\s+me\s+synchronis\w*\s+(a|avec|to)\s+obsidian\b",
        r"\b(peux|peut)\s+tu\s+me\s+synchronis\w*\s+obsidian\b",
        r"\b(peux|peut)\s+tu\s+me\s+connect\w*\s+a\s+obsidian\b",
        r"\bsynchronis\w*\s+(a|avec|to)\s+obsidian\b",
        r"\bsynchronis\w*\s+obsidian\b",
        r"\bsynchronis\w*\s+avec\s+obsidian\b",
        r"\bje\s+veux\s+synchronis\w*\s+avec\s+obsidian\b",
        r"\bconnexion\s+obsidian\b",
        r"\bconnecter\s+a\s+obsidian\b",
        r"\bme\s+connecter\s+a\s+obsidian\b",
        r"\bconnecte[- ]?moi\s+a\s+obsidian\b",
        r"\bconnecte[- ]?toi\s+a\s+obsidian\b",
        r"\b(tu\s+)?peux\s+me\s+connecter\s+a\s+obsidian\b",
        r"\bconnect\w*\s+a\s+obsidian\b",
        r"\bouvr\w*\s+obsidian\b",
        r"\benvoy\w*\s+(ca\s+)?dans\s+obsidian\b",
        r"\bsend\s+to\s+obsidian\b",
        r"\b(sync|connect|connec|synchron|envoy|envoi|ouvr|open|lier|link|relier|acces)\w*.*\bobsidian\b",
        r"\bobsidian\b.*\b(sync|connect|connec|synchron|envoy|envoi|ouvr|open)\w*",
        r"\b(sync obsidian|connecte[- ]?toi|se connecter a obsidian)\b",
    ]
    for pattern in phrase_patterns:
        if re.search(pattern, t):
            return True
    if re.search(r"\b(peux|peut|possible|capable|tu|est-ce|es-ce)\b", t) and (
        re.search(r"\b(sync|connect|connec|synchron)\w*", t)
        or re.search(r"\b(se connecter|me connecter)\b", t)
    ):
        return True
    return False


def _uri_reply_from_html(var_name: str) -> str:
    reply = _html().split(f"var {var_name} =")[1].split(";")[0]
    reply = reply.strip().strip("'")
    return reply.encode("utf-8").decode("unicode_escape").replace("\\u2019", "'")


def _uri_connect_reply_from_html() -> str:
    return _uri_reply_from_html("OC_OBSIDIAN_URI_CONNECT_FR")


def _uri_note_reply_from_html() -> str:
    return _uri_reply_from_html("OC_OBSIDIAN_URI_NOTE_FR")


OC_OBSIDIAN_URI_DENIAL_PHRASES = (
    "Non, je ne peux pas synchroniser avec Obsidian",
    "je ne peux pas vous connecter à Obsidian",
    "aucune synchronisation",
    "aucune capacité Obsidian",
    "pas de connecteur Obsidian",
    "aucun connecteur Obsidian actif",
    "Obsidian indisponible",
    "API Obsidian n'est pas active",
    "I cannot sync",
    "cannot be triggered automatically",
    "press the button yourself",
)


def test_obsidian_sync_intent_synchroniser_a_obsidian_with_prebuilt_uri():
    phrase = "Peux tu me synchroniser à Obsidian ?"
    assert _detect_obsidian_connect_intent(phrase)

    html = _html()
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocDetectObsidianConnectIntent(text)" in send_fn
    assert "ocAddObsidianConnectAssistantMessage(text)" in send_fn
    assert "[COCO] Obsidian intent intercepted before /chat" in send_fn

    handoff_fn = html.split("function ocBuildObsidianUriHandoff")[1].split(
        "function ocRenderObsidianUriAssistantMessage"
    )[0]
    assert "ocBuildObsidianNewNoteUri" in handoff_fn
    assert "ocGetObsidianHandoffAssistantText" in handoff_fn
    assert "userText: userText" in handoff_fn

    render_fn = html.split("function ocRenderObsidianUriAssistantMessage")[1].split(
        "function ocAddObsidianConnectAssistantMessage"
    )[0]
    assert "ocBuildObsidianSyncButton(handoff.uri" in render_fn
    sync_btn_fn = html.split("function ocBuildObsidianSyncButton")[1].split(
        "function ocObsidianNoteTitlePath"
    )[0]
    assert "data-obsidian-uri" in sync_btn_fn
    assert "obsidian://new" in html

    uri_fn = html.split("function ocBuildObsidianNewNoteUri")[1].split(
        "function ocCopyObsidianMarkdown"
    )[0]
    assert "params.set('vault'" in uri_fn
    assert "params.set('name'" in uri_fn
    assert "params.set('content'" in uri_fn

    reply = _uri_connect_reply_from_html()
    assert "Sync Obsidian" in reply
    assert "Markdown" in reply
    for denial in OC_OBSIDIAN_URI_DENIAL_PHRASES:
        assert denial not in reply


def test_obsidian_sync_defaults_uri_enabled():
    from app.core.obsidian_sync import get_obsidian_sync_status

    st = get_obsidian_sync_status()
    assert st["enabled"] is True
    assert st["sync_enabled"] is False
    assert st["mode"] == "uri"
    assert st["vault_name"] == "OpenChawn"
    assert st["default_folder"] == "COCO"
    assert st["uri_open_available"] is True


def test_obsidian_sync_can_be_disabled(monkeypatch):
    from app.core.obsidian_sync import get_obsidian_sync_status

    monkeypatch.setenv("OBSIDIAN_ENABLED", "false")
    st = get_obsidian_sync_status()
    assert st["enabled"] is False
    assert st["uri_open_available"] is False


def test_api_obsidian_sync_status_no_secrets():
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/obsidian-sync/status")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "enabled",
        "mode",
        "vault_name",
        "default_folder",
        "sync_enabled",
        "configured",
        "uri_open_available",
    }
    assert data["enabled"] is True
    assert data["sync_enabled"] is False
    assert "token" not in str(data).lower()
    assert "27124" not in str(data)
    assert "OBSIDIAN_LOCAL_REST_API_TOKEN" not in _html()


def test_ui_affine_and_obsidian_chips_separate():
    html = _html()
    assert "Ouvrir AFFiNE" in html
    assert "Sync Obsidian" in html
    assert 'data-coco-action="open-affine-second-brain"' in html
    assert 'data-coco-action="open-obsidian-sync"' in html
    assert "coco-obsidian-sync-btn" in html
    assert "coco-second-brain-btn" in html


def test_oc_build_obsidian_new_note_uri_includes_encoded_name_and_content():
    block = _obsidian_block()
    assert "function ocBuildObsidianNewNoteUri" in block
    assert "URLSearchParams" in block
    assert "obsidian://new" in block
    assert "params.set('name'" in block
    assert "params.set('content'" in block


def test_oc_build_obsidian_new_note_uri_omits_missing_vault():
    block = _obsidian_block()
    assert "if (opts.vault)" in block
    assert "vault: cfg.vault_name || ''" in block


def test_oc_build_obsidian_markdown_note_structure():
    block = _obsidian_block()
    assert "function ocBuildObsidianMarkdownNote" in block
    assert "COCO / OpenChawn" in block
    assert "Demande utilisateur" in block
    assert "Réponse COCO" in block
    assert "OC_OBSIDIAN_URI_MAX_CONTENT" in block
    assert "tronqué pour respecter la limite URI Obsidian" in block


def test_oc_sync_obsidian_builds_uri_with_encoded_content():
    block = _obsidian_block()
    assert "function ocSyncObsidian" in _html()
    assert "ocBuildObsidianNewNoteUri" in block
    assert "data-obsidian-uri" in block
    assert "ocBuildObsidianNoteMarkdown" in block


def test_ui_no_false_obsidian_sync_success_messages():
    block = _obsidian_block()
    assert "note synchronisée" not in block
    assert "écrit dans Obsidian" not in block
    assert "sync réussie" not in block
    assert "Synchronisation réussie" not in block
    assert "Obsidian sync complete" not in block
    assert "OC_OBSIDIAN_URI_OPENED_FR" in _html()
    assert "/api/obsidian-sync/status" in _html()


def test_oc_sync_obsidian_in_flight_guard():
    block = _obsidian_block()
    assert "ocObsidianOpenInFlight" in block
    assert "800" in block


def test_affine_open_path_unchanged():
    html = _html()
    open_fn = html.split("function ocOpenAffineSecondBrain")[1].split("var ocObsidianSyncConfig")[0]
    assert "window.location.href" not in open_fn
    assert "window.open(affineUrl" in open_fn


def test_build_obsidian_sync_context_uri_mode_default():
    from app.core.obsidian_sync import build_obsidian_sync_context

    ctx = build_obsidian_sync_context()
    low = ctx.lower()
    assert "obsidian uri mode" in low
    assert "sync obsidian" in low
    assert "markdown" in low
    assert "obsidian://new" in low
    assert "name=" in low or "name and content" in low
    assert "do not deny obsidian connectivity" in low
    assert "forbidden when uri mode is active" in low
    assert "local device handoff" in low
    assert "user validates final save" in low
    assert "note/save intent" in low
    assert "travaille dans obsidian" in low
    assert "je ne peux pas vous connecter à obsidian" in low
    assert "obsidian indisponible" in low
    assert "pas de connecteur obsidian" in low
    assert "never claim from chat alone" in low


def test_build_obsidian_sync_context_uri_mode_explicit(monkeypatch):
    from app.core.obsidian_sync import build_obsidian_sync_context

    monkeypatch.setenv("OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("OBSIDIAN_MODE", "uri")
    monkeypatch.setenv("OBSIDIAN_SYNC_ENABLED", "false")
    ctx = build_obsidian_sync_context()
    assert "OBSIDIAN_MODE=uri" in ctx
    assert "Sync Obsidian" in ctx
    assert "answer YES equivalent to" in ctx


def test_build_obsidian_sync_context_disabled(monkeypatch):
    from app.core.obsidian_sync import build_obsidian_sync_context

    monkeypatch.setenv("OBSIDIAN_ENABLED", "false")
    ctx = build_obsidian_sync_context()
    low = ctx.lower()
    assert "not configured" in low
    assert "obsidian uri mode" not in low


def test_build_obsidian_sync_context_local_rest_conservative(monkeypatch):
    from app.core.obsidian_sync import build_obsidian_sync_context

    monkeypatch.setenv("OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("OBSIDIAN_MODE", "local_rest")
    monkeypatch.setenv("OBSIDIAN_SYNC_ENABLED", "true")
    ctx = build_obsidian_sync_context()
    assert "connector confirmation" in ctx.lower()
    assert "sync réussie" in ctx
    assert "note écrite dans Obsidian" in ctx


def test_coco_system_prompt_includes_obsidian_sync():
    from app.api.chat import build_openchawn_base_system_prompt

    prompt = build_openchawn_base_system_prompt()
    assert "OBSIDIAN_SYNC_RUNTIME_MARKER" in prompt
    assert "Obsidian URI mode" in prompt
    assert "Sync Obsidian" in prompt


def test_obsidian_note_intent_phrases_detected():
    phrases = [
        "note ça dans Obsidian",
        "ajoute ça dans Obsidian",
        "sauvegarde dans Obsidian",
        "écris ça dans Obsidian",
        "crée une note Obsidian",
        "mets ça dans Obsidian",
        "enregistre dans Obsidian",
        "Es ce que tu peux maintenant travailler dans Obsidian ?",
    ]
    for phrase in phrases:
        assert _detect_obsidian_note_intent(phrase), phrase


def test_obsidian_note_intent_reply_contract():
    reply = _uri_note_reply_from_html()
    assert "Markdown" in reply
    assert "Sync Obsidian" in reply
    assert "sync réussie" not in reply.lower()
    assert "note écrite" not in reply.lower()
    for denial in OC_OBSIDIAN_URI_DENIAL_PHRASES:
        assert denial not in reply

    html = _html()
    handoff_fn = html.split("function ocBuildObsidianUriHandoff")[1].split(
        "function ocRenderObsidianUriAssistantMessage"
    )[0]
    render_fn = html.split("function ocRenderObsidianUriAssistantMessage")[1].split(
        "function ocAddObsidianConnectAssistantMessage"
    )[0]
    assert "ocBuildObsidianNewNoteUri" in handoff_fn
    assert "ocBuildObsidianSyncButton(handoff.uri" in render_fn


def test_obsidian_connect_intent_uri_aware_in_ui():
    html = _html()
    assert "function ocDetectObsidianNoteIntent" in html
    assert "function ocDetectObsidianConnectIntent" in html
    assert "function ocAddObsidianConnectAssistantMessage" in html
    assert "function ocAddObsidianNoteAssistantMessage" in html
    assert "OC_OBSIDIAN_URI_CONNECT_FR" in html
    assert "OC_OBSIDIAN_URI_NOTE_FR" in html
    assert "votre appareil" in html
    assert "obsidian://new" in html
    assert "bouton Sync Obsidian" in html
    assert "ocNormalizeObsidianIntentText" in html
    assert "faire\\s+le\\s+sync\\s+avec\\s+obsidian" in html
    assert "send\\s+to\\s+obsidian" in html
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocDetectObsidianNoteIntent(text)" in send_fn
    assert "ocAddObsidianNoteAssistantMessage(text)" in send_fn
    assert "ocDetectObsidianConnectIntent(text)" in send_fn
    assert "ocAddObsidianConnectAssistantMessage(text)" in send_fn
    connect_fn = html.split("function ocRenderObsidianUriAssistantMessage")[1].split(
        "function ocAddObsidianConnectAssistantMessage"
    )[0]
    assert "sync réussie" not in connect_fn
    assert "note écrite" not in connect_fn
    assert "ocBuildObsidianSyncButton(handoff.uri" in connect_fn
    assert "data-obsidian-uri" in html
    for phrase in OC_OBSIDIAN_URI_DENIAL_PHRASES:
        assert phrase not in connect_fn


def test_obsidian_connect_intent_french_english_variants():
    phrases = [
        "sync avec Obsidian",
        "faire le sync avec Obsidian",
        "faire la sync avec Obsidian",
        "synchroniser avec Obsidian",
        "synchronise avec Obsidian",
        "connexion Obsidian",
        "connecter à Obsidian",
        "connecte toi à Obsidian",
        "envoyer dans Obsidian",
        "envoie ça dans Obsidian",
        "send to Obsidian",
        "sync to Obsidian",
        "Est-ce que tu peux maintenant faire le sync avec Obsidian ?",
    ]
    for phrase in phrases:
        assert _detect_obsidian_connect_intent(phrase), phrase


def test_obsidian_connect_intent_exact_user_phrase_reply_contract():
    phrase = "Est-ce que tu peux maintenant faire le sync avec Obsidian ?"
    assert _detect_obsidian_connect_intent(phrase)
    _assert_uri_connect_reply_contract()


def test_obsidian_connect_intent_typo_connect_phrases():
    phrases = [
        "Es ce que tu peux me connecter à Obsidian ?",
        "Connecte moi à Obsidian",
        "Je veux synchroniser avec Obsidian",
    ]
    for phrase in phrases:
        assert _detect_obsidian_connect_intent(phrase), phrase
    _assert_uri_connect_reply_contract()


def _assert_uri_connect_reply_contract() -> None:
    reply = _uri_connect_reply_from_html()
    assert "Markdown" in reply
    assert "Sync Obsidian" in reply
    assert "votre appareil" in reply
    for denial in OC_OBSIDIAN_URI_DENIAL_PHRASES:
        assert denial not in reply
