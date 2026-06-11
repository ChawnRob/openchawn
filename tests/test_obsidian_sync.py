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
    return t.replace("\u2019", "'").replace("'", "'")


def _detect_obsidian_connect_intent(text: str) -> bool:
    """Mirror of ocDetectObsidianConnectIntent in static/index.html."""
    t = _normalize_obsidian_intent_text(text).strip()
    if not t or not re.search(r"\bobsidian\b", t):
        return False
    if re.search(r"\baffine\b", t) and not re.search(
        r"\bobsidian\b", re.sub(r"\baffine\b", "", t)
    ):
        return False
    phrase_patterns = [
        r"\bsync\s+(avec|to)\s+obsidian\b",
        r"\bfaire\s+le\s+sync\s+avec\s+obsidian\b",
        r"\bfaire\s+la\s+sync\s+avec\s+obsidian\b",
        r"\bsynchronis\w*\s+avec\s+obsidian\b",
        r"\bconnexion\s+obsidian\b",
        r"\bconnect\w*\s+a\s+obsidian\b",
        r"\bconnecte[- ]?toi\s+a\s+obsidian\b",
        r"\benvoy\w*\s+(ca\s+)?dans\s+obsidian\b",
        r"\bsend\s+to\s+obsidian\b",
        r"\bsync\s+obsidian\b",
        r"\b(sync|connect|connec|synchron|envoy|envoi|ouvr|open|lier|link|relier|acces)\w*.*\bobsidian\b",
        r"\bobsidian\b.*\b(sync|connect|connec|synchron|envoy|envoi|ouvr|open)\w*",
        r"\b(sync obsidian|connecte[- ]?toi|se connecter a obsidian)\b",
    ]
    for pattern in phrase_patterns:
        if re.search(pattern, t):
            return True
    if re.search(r"\b(peux|peut|possible|capable|tu|est-ce)\b", t) and (
        re.search(r"\b(sync|connect|connec|synchron)\w*", t)
        or re.search(r"\bse connecter\b", t)
    ):
        return True
    return False


OC_OBSIDIAN_URI_CONNECT_EXPECTED = (
    "Oui, je peux préparer une note Markdown depuis cette conversation et déclencher "
    "l'ouverture d'Obsidian via le bouton Sync Obsidian. En mode actuel, je ne peux pas "
    "confirmer une synchronisation profonde dans le vault : j'utilise obsidian://new pour "
    "ouvrir Obsidian avec le contenu préparé."
)

OC_OBSIDIAN_URI_DENIAL_PHRASES = (
    "Non, je ne peux pas synchroniser avec Obsidian",
    "aucune capacité Obsidian",
    "aucun connecteur Obsidian actif",
    "API Obsidian n'est pas active",
)


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


def test_oc_sync_obsidian_builds_uri_with_encoded_content():
    block = _obsidian_block()
    assert "function ocSyncObsidian" in _html()
    assert "obsidian://new?vault=" in block
    assert "&name=" in block
    assert "&content=" in block
    assert "encodeURIComponent(markdown)" in block
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
    assert "do not deny obsidian connectivity" in low
    assert "forbidden when uri mode is active" in low
    assert "depuis cette conversation" in low
    assert "obsidian://new" in low
    assert "non, je ne peux pas synchroniser avec obsidian" in low
    assert "aucune capacité obsidian" in low
    assert "never claim from chat alone" in low


def test_build_obsidian_sync_context_uri_mode_explicit(monkeypatch):
    from app.core.obsidian_sync import build_obsidian_sync_context

    monkeypatch.setenv("OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("OBSIDIAN_MODE", "uri")
    monkeypatch.setenv("OBSIDIAN_SYNC_ENABLED", "false")
    ctx = build_obsidian_sync_context()
    assert "OBSIDIAN_MODE=uri" in ctx
    assert "Sync Obsidian" in ctx
    assert "answer YES with substance" in ctx


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


def test_obsidian_connect_intent_uri_aware_in_ui():
    html = _html()
    assert "function ocDetectObsidianConnectIntent" in html
    assert "function ocAddObsidianConnectAssistantMessage" in html
    assert "OC_OBSIDIAN_URI_CONNECT_FR" in html
    assert "depuis cette conversation" in html
    assert "obsidian://new" in html
    assert "bouton Sync Obsidian" in html
    assert "faire\\s+le\\s+sync\\s+avec\\s+obsidian" in html
    assert "send\\s+to\\s+obsidian" in html
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocDetectObsidianConnectIntent(text)" in send_fn
    assert "ocAddObsidianConnectAssistantMessage()" in send_fn
    connect_fn = html.split("function ocAddObsidianConnectAssistantMessage")[1].split(
        "function ocAddAffineOpenAssistantMessage"
    )[0]
    assert "sync réussie" not in connect_fn
    assert "note écrite" not in connect_fn
    assert "open-obsidian-sync" in connect_fn
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

    html = _html()
    reply = html.split("var OC_OBSIDIAN_URI_CONNECT_FR =")[1].split(";")[0]
    reply = reply.strip().strip("'")
    reply = reply.encode("utf-8").decode("unicode_escape").replace("\\u2019", "'")

    assert "Markdown" in reply
    assert "Sync Obsidian" in reply
    assert "obsidian://new" in reply
    assert "synchronisation profonde" in reply
    for denial in OC_OBSIDIAN_URI_DENIAL_PHRASES:
        assert denial not in reply
