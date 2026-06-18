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
    assert "ocApplyCocoStateEl(headerEl" in set_fn
    assert "ocApplyCocoStateEl(companionEl" in set_fn
    assert "ocGetCocoReadyStateLabel()" in set_fn
    assert "ocApplyCocoStateEl(companionEl, state, companionText, false)" in set_fn
    companion_block = set_fn.split("ocApplyCocoStateEl(companionEl")[1].split("ocSyncWelcomeHome")[0]
    assert "ocGetCocoReadyStateLabel" not in companion_block
    assert "ocGetCurrentUserDisplayName" not in companion_block


def test_companion_ready_label_hidden_when_connected_mobile():
    html = _html()
    assert "oc-session-connected" in html
    assert "document.documentElement.classList.toggle('oc-session-connected', connected)" in html
    block = html.split(
        "html.ux-chat-clean.oc-session-connected .welcome.hero-cockpit .coco-companion-presence.coco-state-ready .coco-state-label"
    )[1].split("}")[0]
    assert "clip: rect" in block or "clip-path" in block


def test_welcome_home_sync_helpers():
    html = _html()
    assert "function ocShouldShowMobileWelcomeHome()" in html
    should = html.split("function ocShouldShowMobileWelcomeHome()")[1].split("function ocSyncWelcomeHome")[0]
    assert "oc-chat-empty" in should
    assert "ocIsConnectedSession()" in should
    assert "ocChatCleanMobileComposer()" in should

    sync = html.split("function ocSyncWelcomeHome()")[1].split("function ocApplyCocoStateEl")[0]
    assert "oc-welcome-home-active" in sync
    assert "document.documentElement.classList.toggle('oc-welcome-home-shell', show)" in sync
    assert "Bonjour " in sync
    assert "ocGetWelcomeDisplayName()" in sync
    auth_sync = html.split("function ocSyncAuthHeaderButtons()")[1].split("function ocHasLocalOwnerToken")[0]
    assert "ocSyncWelcomeHome()" in auth_sync


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


def test_regression_old_duplicate_identity_pattern_removed():
    """Échoue si ocSetCocoState réapplique le label header (● JAROD) au companion."""
    html = _html()
    set_fn = html.split("function ocSetCocoState(state, label)")[1].split("function ocMsgRoleLabel")[0]
    assert "forEach(function (el, idx)" not in set_fn
    assert "lab.textContent = text" not in set_fn or "ocApplyCocoStateEl" in set_fn
    assert ".coco-state-label, .coco-header-state-label" not in set_fn
    html = _html()
    marker = "document.getElementById('ocWelcomeQuickActions')?.addEventListener('click'"
    assert marker in html
    handler = html.split(marker)[1].split("// COCO v1.2 message actions")[0]
    assert "ocRefillComposerPrompt(prompt)" in handler
    assert "data-coco-prompt" in handler
