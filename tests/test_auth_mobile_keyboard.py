"""Mobile auth form must scroll above iOS keyboard without hiding or resizing it."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_auth_screen_scrollable_on_mobile():
    html = _html()
    block = html.split("/* ── Auth (light cards) ── */")[1].split(".welcome.auth-hero-mini .welcome-icon")[0]
    assert ".auth-screen" in block
    mobile_auth = block.split("@media (max-width: 640px)")[1]
    assert "overflow-y: auto" in mobile_auth.split(".auth-screen")[1]
    assert "-webkit-overflow-scrolling: touch" in mobile_auth.split(".auth-screen")[1]
    assert "max-height: 100dvh" in mobile_auth.split(".auth-screen")[1]
    assert "max-height: calc(100dvh" in mobile_auth.split(".auth-box")[1]


def test_mobile_auth_input_focus_handler_exists():
    html = _html()
    assert "function ocInitAuthMobileKeyboardUi()" in html
    fn = html.split("function ocInitAuthMobileKeyboardUi()")[1].split("function showAuthForLogin")[0]
    assert "focusin" in fn
    assert "ocScrollAuthFieldIntoView" in fn
    scroll_fn = html.split("function ocScrollAuthFieldIntoView")[1].split("function ocInitAuthMobileKeyboardUi")[0]
    assert "block: 'center'" in scroll_fn
    assert "behavior: 'smooth'" in scroll_fn
    assert "setTimeout" in scroll_fn


def test_visual_viewport_keyboard_padding_without_keyboard_hacks():
    html = _html()
    assert "function ocAuthKeyboardInsetPx()" in html
    assert "window.visualViewport" in html
    pad_fn = html.split("function ocApplyAuthKeyboardPadding()")[1].split("function ocResetAuthKeyboardPadding")[0]
    assert "paddingBottom" in pad_fn
    assert "oc-auth-keyboard-open" in pad_fn
    # Must not resize viewport, hide keyboard, or force input types globally
    assert 'content="width=device-width, initial-scale=1.0, viewport-fit=cover"' in html
    assert "visualViewport.addEventListener('resize'" in html
    lowered = html.lower()
    assert "keyboard" not in lowered or "oc-auth-keyboard-open" in html
    assert "inputmode=none" not in lowered
    assert "readonly" not in html.split("function ocInitAuthMobileKeyboardUi()")[1].split("function showAuthForLogin")[0]


def test_password_field_scroll_and_optional_toggle():
    html = _html()
    assert 'class="auth-password-wrap"' in html
    assert 'id="loginPassword"' in html
    assert 'type="password"' in html.split('id="loginPassword"')[0][-80:]
    assert "auth-password-toggle" in html
    toggle_block = html.split("function ocInitAuthMobileKeyboardUi()")[1].split("function showAuthForLogin")[0]
    assert "input.type = show ? 'text' : 'password'" in toggle_block
    scroll_fn = html.split("function ocScrollAuthFieldIntoView")[1].split("function ocInitAuthMobileKeyboardUi")[0]
    assert "scrollIntoView" in scroll_fn


def test_quota_auth_behavior_still_works():
    html = _html()
    send_block = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocIsGuestQuotaLimitError(r.status, detail)" in send_block
    assert "showAuthForLogin()" in send_block.split("ocIsGuestQuotaLimitError")[1][:400]
    assert "ocInitAuthMobileKeyboardUi()" in html.split("function showAuthForLogin")[1][:400]


def test_composer_controls_unchanged():
    html = _html()
    assert "function ocSyncMobileComposerActionButton()" in html
    assert "oc-composer-action-mic" in html
    assert 'id="btnFileIntake"' in html
    mobile = html.split("/* V11.6.3 mobile composer vertical alignment fix */")[1].split("@media (max-width: 896px)")[0]
    assert "html.ux-chat-clean .clean-input-shell .input-wrapper #btnSpeech" in mobile
