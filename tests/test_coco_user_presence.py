"""COCO presence badge shows connected user name after login."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_oc_get_current_user_display_name_helper():
    html = _html()
    assert "function ocGetCurrentUserDisplayName()" in html
    fn = html.split("function ocGetCurrentUserDisplayName()")[1].split("function ocIsAuthenticatedAccount")[0]
    assert "display_name" in fn
    assert "indexOf('@')" in fn or "indexOf(\"@\")" in fn
    assert "split(/\\s+/)" in fn


def test_coco_ready_label_guest_vs_authenticated():
    html = _html()
    assert "function ocGetCocoReadyStateLabel()" in html
    fn = html.split("function ocGetCocoReadyStateLabel()")[1].split("function ocSetCocoState")[0]
    assert "return 'Ready'" in fn
    assert "\\u25cf" in fn or "●" in fn
    set_fn = html.split("function ocSetCocoState(state, label)")[1].split("function ocMsgRoleLabel")[0]
    assert "state === 'ready'" in set_fn
    assert "ocGetCocoReadyStateLabel()" in set_fn


def test_enter_chat_and_guest_chat_refresh_coco_ready_label():
    html = _html()
    enter_chat = html.split("function enterChat()")[1].split("function enterGuestChat")[0]
    enter_guest = html.split("function enterGuestChat()")[1].split("document.getElementById('ocGuestAuthBtn')")[0]
    assert "ocSetCocoState('ready')" in enter_chat
    assert "ocSetCocoState('ready')" in enter_guest


def test_user_record_from_session_storage():
    html = _html()
    fn = html.split("function ocGetCurrentUserRecord()")[1].split("function ocGetCurrentUserDisplayName")[0]
    assert "sessionStorage.getItem('oc_user')" in fn
    assert "currentUser" in fn


def test_login_stores_user_before_enter_chat():
    html = _html()
    login = html.split("async function doLogin()")[1].split("// ── Register")[0]
    assert "sessionStorage.setItem('oc_user'" in login
    assert "currentUser = d.user" in login
    assert "enterChat()" in login
