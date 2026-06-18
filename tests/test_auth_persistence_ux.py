"""Mobile auth persistence — hydrate JWT/owner session after refresh, logout, invalid token."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _auth_block() -> str:
    return _html().split("// ── Auth helpers ─────────────────────────────────────")[1].split(
        "// ── Dictée locale"
    )[0]


def test_auth_storage_helpers_present():
    block = _auth_block()
    assert "function ocHydrateAuthFromStorage()" in block
    assert "function ocPersistAuthSession(" in block
    assert "function ocClearAuthSession()" in block
    assert "function ocGetStoredJwt()" in block
    assert "localStorage.setItem(OC_AUTH_TOKEN_KEY" in block
    assert "localStorage.setItem(OC_AUTH_USER_KEY" in block


def test_boot_hydrates_before_guest_fallback():
    boot = _html().split("async function boot()")[1].split("boot();")[0]
    assert "ocHydrateAuthFromStorage()" in boot
    assert "tryAutoLogin()" in boot
    assert "tryRestoreOwnerSession()" in boot
    assert boot.index("ocHydrateAuthFromStorage()") < boot.index("enterGuestChat()")


def test_try_auto_login_uses_providers_status_not_history():
    fn = _html().split("async function tryAutoLogin()")[1].split("async function tryRestoreOwnerSession")[0]
    assert "/providers/status" in fn
    assert "/history" not in fn
    assert "ocJwtLooksValid" in fn
    assert "ocClearAuthSession()" in fn


def test_refresh_without_token_shows_connexion():
    guest = _html().split("function enterGuestChat()")[1].split("document.getElementById('ocGuestAuthBtn')")[0]
    sync = _html().split("function ocSyncAuthHeaderButtons()")[1].split("function ocHasLocalOwnerToken")[0]
    assert "Connexion" in sync
    assert "ocIsConnectedSession()" in _html().split("function ocSyncGuestAuthHeaderBtn()")[1].split("function ocAuthKeyboardInsetPx")[0]


def test_logout_clears_storage_and_returns_guest_connexion():
    logout = _html().split("dom.logoutBtn.addEventListener('click'")[1].split("// ── Load profiles")[0]
    clear_fn = _auth_block().split("function ocClearAuthSession()")[1].split("function ocDecodeJwtPayload")[0]
    assert "ocClearAuthSession()" in logout
    assert "enterGuestChat()" in logout
    assert "localStorage.removeItem('oc_owner_token')" in clear_fn
    assert "localStorage.removeItem(OC_AUTH_TOKEN_KEY)" in clear_fn


def test_invalid_token_fallback_clears_session():
    fn = _html().split("async function tryAutoLogin()")[1].split("async function tryRestoreOwnerSession")[0]
    assert "if (!ocJwtLooksValid(jwt))" in fn
    assert "ocClearAuthSession()" in fn
    api = _html().split("async function apiFetch(path, opts = {})")[1].split("// ── Toggle auth forms")[0]
    assert "ocClearAuthSession()" in api
    assert "showAuthForLogin()" in api


def test_mobile_header_hides_connexion_when_session_valid():
    guest_sync = _html().split("function ocSyncGuestAuthHeaderBtn()")[1].split("function ocAuthKeyboardInsetPx")[0]
    assert "!ocIsConnectedSession()" in guest_sync
    assert "oc-guest-auth-visible" in guest_sync


def test_login_persists_to_local_and_session_storage():
    login = _html().split("async function doLogin()")[1].split("// ── Register")[0]
    register = _html().split("async function doRegister()")[1].split("// ── Logout")[0]
    assert "ocPersistAuthSession" in login
    assert "ocPersistAuthSession" in register


def test_owner_session_restored_on_boot():
    fn = _html().split("async function tryRestoreOwnerSession()")[1].split("async function boot()")[0]
    assert "ocHasLocalOwnerToken()" in fn
    assert "enterGuestChat()" in fn
    after_chat = _html().split("function ocSyncSysBarAfterChat(payload)")[1].split("function authHeaders")[0]
    assert "OC_OWNER_SESSION_VALID_KEY" in after_chat
    assert "ocSyncAuthHeaderButtons()" in after_chat


def test_connected_user_shows_header_logout_button():
    html = _html()
    assert 'id="ocHeaderLogoutBtn"' in html
    assert "oc-header-logout-btn" in html
    assert "oc-header-status-cluster" in html
    sync = html.split("function ocSyncAuthHeaderButtons()")[1].split("function ocHasLocalOwnerToken")[0]
    assert "headerLogoutBtn" in sync
    assert "oc-auth-logout-visible" in sync
    assert "Déconnexion" in sync
    css = html.split("html.ux-chat-clean .oc-header-logout-btn {")[1].split("html.ux-chat-clean .oc-header-logout-btn.oc-auth-logout-visible")[0]
    assert "min-height: 44px" in css
    assert "min-width: 44px" in css


def test_connected_owner_shows_header_logout_hidden_connexion():
    guest_sync = _html().split("function ocSyncGuestAuthHeaderBtn()")[1].split("function ocAuthKeyboardInsetPx")[0]
    assert "!ocIsConnectedSession()" in guest_sync
    sync = _html().split("function ocSyncAuthHeaderButtons()")[1].split("function ocHasLocalOwnerToken")[0]
    assert "dom.headerLogoutBtn.classList.toggle('oc-auth-logout-visible', connected)" in sync


def test_guest_hides_header_logout_shows_connexion():
    sync = _html().split("function ocSyncAuthHeaderButtons()")[1].split("function ocHasLocalOwnerToken")[0]
    assert "dom.headerLogoutBtn.classList.toggle('hidden', !connected)" in sync


def test_logout_click_handler_shared_and_clears_storage():
    html = _html()
    assert "function ocHandleLogoutClick()" in html
    assert "dom.headerLogoutBtn?.addEventListener('click', ocHandleLogoutClick)" in html
    assert "dom.logoutBtn.addEventListener('click', ocHandleLogoutClick)" in html
    handler = html.split("async function ocHandleLogoutClick()")[1].split("dom.logoutBtn.addEventListener")[0]
    assert "ocClearAuthSession()" in handler
    assert "enterGuestChat()" in handler


def test_boot_restore_calls_auth_header_sync_via_enter_chat():
    enter = _html().split("function enterChat()")[1].split("// ── Enter chat (invité)")[0]
    guest = _html().split("function enterGuestChat()")[1].split("document.getElementById('ocGuestAuthBtn')")[0]
    assert "ocSyncAuthHeaderButtons()" in enter
    assert "ocSyncAuthHeaderButtons()" in guest

