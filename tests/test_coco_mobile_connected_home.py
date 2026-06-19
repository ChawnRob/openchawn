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


def test_welcome_analyze_image_triggers_file_intake():
    html = _html()
    cards = html.split('id="ocWelcomeQuickActions"')[1].split("</div>")[0]
    assert 'data-coco-welcome-action="analyze-image"' in cards
    assert "Analyse cette image et résume" not in cards

    handler_fn = html.split("function ocHandleWelcomeQuickAction(card, ev)")[1].split("function ocShowCopyConfirmation")[0]
    assert "welcomeAction === 'analyze-image'" in handler_fn
    assert "ocTriggerFileIntakeFromWelcome(ev)" in handler_fn

    trigger_fn = html.split("function ocTriggerFileIntakeFromWelcome(ev)")[1].split("function ocHandleWelcomeQuickAction")[0]
    assert "getElementById('btnFileIntake')" in trigger_fn
    assert "attachBtn.click()" in trigger_fn
    assert "ocOpenFileIntakeActionSheet()" in trigger_fn


def test_welcome_affine_launches_workflow_not_prompt():
    html = _html()
    cards = html.split('id="ocWelcomeQuickActions"')[1].split("</div>")[0]
    assert 'data-coco-action="open-affine-second-brain"' in cards
    assert "coco-second-brain-btn" in cards

    handler_fn = html.split("function ocHandleWelcomeQuickAction(card, ev)")[1].split("function ocShowCopyConfirmation")[0]
    assert "cocoAction === 'open-affine-second-brain'" in handler_fn
    assert "ocOpenAffineSecondBrain(card)" in handler_fn
    assert "Analyse cette image" not in handler_fn


def test_welcome_notes_and_study_launch_organizer_workflows():
    html = _html()
    handler_fn = html.split("function ocHandleWelcomeQuickAction(card, ev)")[1].split("function ocShowCopyConfirmation")[0]
    assert "ocStartKnowledgeOrganizer('Organise mes notes de cours')" in handler_fn
    assert "ocStartStudyMode('Fais-moi une fiche de révision')" in handler_fn
    assert "ocRefillComposerPrompt" not in handler_fn

    ko_fn = html.split("function ocStartKnowledgeOrganizer(userText)")[1].split("function ocStartStudyMode")[0]
    assert "ocStartKnowledgeOrganizerWorkflow(userText)" in ko_fn
    study_fn = html.split("function ocStartStudyMode(userText)")[1].split("function ocHandleWelcomeQuickAction")[0]
    assert "ocStartStudyOrganizerWorkflow(userText)" in study_fn

    workflow = html.split("async function ocStartKnowledgeOrganizerWorkflow(userText)")[1].split(
        "async function ocStartStudyOrganizerWorkflow"
    )[0]
    assert "ocHandleKnowledgeOrganizerIntent(text)" in workflow
    assert "addMsg('user', text)" in workflow
    assert "ocRefillComposerPrompt" not in workflow


def test_welcome_home_composer_docked_at_bottom():
    html = _html()
    assert 'id="ocComposerDock"' in html
    assert 'oc-mobile-composer-dock' in html
    assert 'function ocSyncMobileComposerDock' in html

    app_css = html.split('html.ux-chat-clean .app {')[1].split('}')[0]
    assert 'height: 100dvh' in app_css
    assert 'min-height: 100svh' in app_css

    dock_css = html.split('html.ux-chat-clean.oc-mobile-composer-dock .oc-composer-dock {')[1].split('}')[0]
    assert 'flex-shrink: 0' in dock_css
    assert 'padding-bottom: env(safe-area-inset-bottom' in dock_css
    assert 'position: fixed' not in dock_css

    messages_css = html.split(
        'html.ux-chat-clean.oc-mobile-composer-dock .oc-chat-shell .messages.oc-message-list {'
    )[1].split('}')[0]
    assert 'flex: 1' in messages_css
    assert 'overflow-y: auto' in messages_css
    assert 'oc-composer-dock-h' not in messages_css

    assert 'max-height: 700px)' in html
    assert 'min-height: 850px)' in html
    assert 'oc-vv-keyboard-open' in html

    shell = html.split('id="ocChatShell"')[1].split('id="ocSettingsBackdrop"')[0]
    welcome_pos = shell.find('id="welcome"')
    dock_pos = shell.find('id="ocComposerDock"')
    assert welcome_pos > -1 and dock_pos > welcome_pos
    welcome_section = shell[welcome_pos:dock_pos]
    assert 'id="inputArea"' not in welcome_section
    assert 'id="ocComposerDock"' not in welcome_section.split('id="ocWelcomeQuickActions"')[0]


def test_composer_dock_separate_from_welcome_cards():
    html = _html()
    quick = html.split('id="ocWelcomeQuickActions"')[1].split('id="ocComposerDock"')[0]
    assert 'id="inputArea"' not in quick
    assert 'oc-composer-mobile-toolbar' not in quick


def test_mobile_viewport_flex_architecture():
    html = _html()
    header_block = html.split('html.ux-chat-clean .header {')[1].split('}')[0]
    assert 'flex-shrink: 0' in header_block

    sync_fn = html.split('function ocSyncMobileComposerDock()')[1].split('function ocUxInitChatShell')[0]
    assert 'oc-vv-keyboard-open' in sync_fn
    assert 'visualViewport' in sync_fn
    assert 'oc-composer-dock-h' not in sync_fn
    assert "dockWrap.style.bottom" not in sync_fn


def test_guest_and_authenticated_share_composer_dock_shell():
    html = _html()
    assert html.count('id="ocComposerDock"') == 1
    assert html.count('id="ocChatShell"') == 1
    sync = html.split('function ocSyncChatCleanLayout()')[1].split('function ocSyncMobileComposerDock')[0]
    assert 'ocSyncMobileComposerDock()' in sync
    enter_chat = html.split('function enterChat()')[1].split('function enterGuestChat')[0]
    enter_guest = html.split('function enterGuestChat()')[1].split("document.getElementById('ocGuestAuthBtn')")[0]
    assert 'ocSyncChatCleanLayout()' in enter_chat
    assert 'ocSyncChatCleanLayout()' in enter_guest


def test_welcome_cards_no_parasite_prompt_in_composer():
    html = _html()
    cards = html.split('id="ocWelcomeQuickActions"')[1].split("</div>")[0]
    assert 'data-coco-prompt=' not in cards
    handler_fn = html.split("function ocHandleWelcomeQuickAction(card, ev)")[1].split("function ocShowCopyConfirmation")[0]
    assert "ocRefillComposerPrompt" not in handler_fn
    listener = html.split("document.getElementById('ocWelcomeQuickActions')?.addEventListener('click'")[1].split("// COCO v1.2 message actions")[0]
    assert "ocHandleWelcomeQuickAction(card, e)" in listener


def test_welcome_obsidian_affine_chips_still_present_for_mobile():
    html = _html()
    assert 'data-coco-action="open-obsidian-sync"' in html
    assert 'data-coco-action="open-affine-second-brain"' in html
    assert 'id="btnFileIntake"' in html
    obsidian = html.split("function ocSyncObsidian")[1].split("document.addEventListener('click'")[0]
    assert "obsidian" in obsidian.lower()
