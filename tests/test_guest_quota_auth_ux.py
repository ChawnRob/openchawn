"""Guest quota exhaustion must surface auth UX, not a generic transmission error."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_oc_is_guest_quota_limit_error_helper_present():
    html = _html()
    assert "function ocIsGuestQuotaLimitError(status, detail)" in html
    body = html.split("function ocIsGuestQuotaLimitError(status, detail)")[1].split("function ocSyncGuestAuthHeaderBtn")[0]
    assert "Number(status) !== 429" in body
    assert "limite gratuite" in body


def test_send_handles_quota_429_with_auth_not_transmission_failed():
    html = _html()
    send_block = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    quota_branch = send_block.split("if (ocIsGuestQuotaLimitError(r.status, detail))")[1].split("} else {")[0]
    assert "showAuthForLogin()" in quota_branch
    assert "quota-auth" in quota_branch
    assert "TRANSMISSION FAILED" not in quota_branch
    assert "Tu as atteint la limite gratuite" in quota_branch


def test_quota_limit_message_actions_exclude_retry():
    html = _html()
    fn = html.split("function ocBuildQuotaLimitMsgActions()")[1].split("function ocGetMsgBodyText")[0]
    assert "Connexion / Inscription" in fn
    assert "open-auth" in fn
    assert "retry-last" not in fn


def test_open_auth_message_action_calls_show_auth():
    html = _html()
    handler = html.split("(function ocCocoMessageActionsV12()")[1].split("})();")[0]
    assert "action === 'open-auth'" in handler
    assert "showAuthForLogin()" in handler.split("action === 'open-auth'")[1][:200]


def test_api_fetch_401_still_opens_auth():
    html = _html()
    api_fetch = html.split("async function apiFetch(path, opts = {})")[1].split("// ── Toggle auth forms")[0]
    assert "if (r.status === 401)" in api_fetch
    assert "showAuthForLogin()" in api_fetch


def test_mobile_chat_clean_has_reachable_guest_auth_entry():
    html = _html()
    assert 'id="ocGuestAuthBtn"' in html
    assert "function ocSyncGuestAuthHeaderBtn()" in html
    sync_fn = html.split("function ocSyncGuestAuthHeaderBtn()")[1].split("function showAuthForLogin")[0]
    assert "isGuestMode" in sync_fn
    assert "ocChatCleanMobileComposer()" in sync_fn
    css = html.split("html.ux-chat-clean .oc-guest-auth-header-btn {")[1].split("/* ── System chips ──")[0]
    assert "@media (max-width: 640px)" in css
    assert "oc-guest-auth-visible" in css
    assert "display: inline-flex !important" in css
    assert "getElementById('ocGuestAuthBtn')" in html
    listener = html.split("document.getElementById('ocGuestAuthBtn')?.addEventListener('click'")[1][:120]
    assert "showAuthForLogin()" in listener


def test_composer_mic_send_attach_controls_unchanged():
    html = _html()
    assert "function ocSyncMobileComposerActionButton()" in html
    assert "oc-composer-action-mic" in html
    assert "oc-composer-action-send" in html
    assert 'id="btnFileIntake"' in html
    mobile = html.split("/* V11.6.3 mobile composer vertical alignment fix */")[1].split("@media (max-width: 896px)")[0]
    assert "html.ux-chat-clean .clean-input-shell .input-wrapper #btnSpeech" in mobile
    assert "display: none !important" in mobile.split("#btnSpeech")[1][:120]
    assert "html.ux-chat-clean .clean-input-shell .input-wrapper > #btnImportPlus" in mobile
