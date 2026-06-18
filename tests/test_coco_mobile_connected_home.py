"""Mobile connected home — single user identity, welcome zone, preserved composer chips."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_welcome_home_markup_and_quick_actions():
    html = _html()
    assert 'id="ocWelcomeHome"' in html
    assert 'id="ocWelcomeGreeting"' in html
    assert 'id="ocWelcomeQuickActions"' in html
    assert "Organiser mes notes" in html
    assert "Travailler avec AFFiNE" in html
    assert "Analyser une image" in html
    assert "Étudier / Réviser" in html
    assert "Que souhaites-tu faire aujourd'hui ?" in html


def test_companion_label_never_uses_user_name():
    html = _html()
    assert "function ocGetCocoCompanionStateLabel(state, label)" in html
    fn = html.split("function ocGetCocoCompanionStateLabel(state, label)")[1].split(
        "function ocGetWelcomeDisplayName"
    )[0]
    assert "return 'COCO'" in fn
    assert "ocGetCurrentUserDisplayName" not in fn

    set_fn = html.split("function ocSetCocoState(state, label)")[1].split("function ocMsgRoleLabel")[0]
    assert "ocGetCocoCompanionStateLabel(state, label)" in set_fn
    assert "idx === 0 ? headerText : companionText" in set_fn
    assert "ocGetCocoReadyStateLabel()" in set_fn


def test_welcome_home_sync_helpers():
    html = _html()
    assert "function ocShouldShowMobileWelcomeHome()" in html
    should = html.split("function ocShouldShowMobileWelcomeHome()")[1].split("function ocSyncWelcomeHome")[0]
    assert "oc-chat-empty" in should
    assert "ocIsConnectedSession()" in should
    assert "ocChatCleanMobileComposer()" in should

    sync = html.split("function ocSyncWelcomeHome()")[1].split("function ocSetCocoState")[0]
    assert "oc-welcome-home-active" in sync
    assert "oc-welcome-home-shell" in sync
    assert "Bonjour " in sync
    assert "ocGetWelcomeDisplayName()" in sync


def test_welcome_home_styles_and_no_center_duplicate():
    html = _html()
    assert ".oc-welcome-home-active" in html
    assert ".oc-welcome-card" in html
    assert "ocWelcomeOrbPulse" in html
    assert "prefers-reduced-motion" in html
    block = html.split("html.ux-chat-clean .welcome.hero-cockpit.oc-welcome-home-active .coco-companion-presence .coco-state-label")[1].split("}")[0]
    assert "clip: rect" in block or "clip-path" in block


def test_header_logout_and_composer_chips_preserved():
    html = _html()
    assert 'id="ocHeaderLogoutBtn"' in html
    assert "Déconnexion" in html
    assert 'data-coco-action="open-affine-second-brain"' in html
    assert 'data-coco-action="open-obsidian-sync"' in html
    assert "Photo/Fichier" in html or "coco-file-intake-chip-label" in html
    assert 'id="input"' in html
    assert 'id="inputArea"' in html


def test_welcome_cards_wire_prompt_refill():
    html = _html()
    marker = "document.getElementById('ocWelcomeQuickActions')?.addEventListener('click'"
    assert marker in html
    handler = html.split(marker)[1].split("// COCO v1.2 message actions")[0]
    assert "ocRefillComposerPrompt(prompt)" in handler
    assert "data-coco-prompt" in handler
