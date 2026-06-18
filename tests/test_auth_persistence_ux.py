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
