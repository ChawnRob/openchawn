"""Memory scope isolation — user/guest boundaries and media_id access control."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.chat import ChatRequest, assemble_chat_generation_inputs
from app.files_intake.image_analysis import ImageAnalysisResult
from app.files_intake.session_image_context import (
    build_last_image_context,
    clear_image_context_store,
    get_last_image_context,
    get_last_image_context_for_user,
    memory_scope_from_user,
    set_last_image_context_scoped,
)
from app.main import app
from app.memory.memory_scope import (
    MemoryScopeError,
    assert_scope_allows_context_key,
    media_id_allowed_for_scope,
    resolve_memory_scope_from_user,
    scope_allows_context_key,
)
from tests.test_files_intake import PNG_MAGIC, _guest_headers, _post_intake, _reset_guest

_MOCK_ANALYSIS = ImageAnalysisResult(
    description="Panneau bleu avec bouton.",
    detected_elements=["bouton"],
    clarification_question=None,
    provider="kimi",
    model="moonshot-v1-8k-vision-preview",
    raw_text="{}",
    fallback_used=False,
)


def _guest_user(session_id: str, ip: str = "10.0.0.1") -> dict:
    return {"is_guest": True, "guest_session_id": session_id, "ip": ip, "user_role": "guest"}


def _auth_user(user_id: int) -> dict:
    return {"is_guest": False, "id": user_id, "user_role": "user", "ip": "10.0.0.2"}


def test_resolve_memory_scope_guest_and_user():
    guest = resolve_memory_scope_from_user(_guest_user("guest_scope_a"))
    assert guest.scope_kind == "guest"
    assert guest.guest_session_id == "guest_scope_a"
    assert guest.context_key == "guest:guest_scope_a"
    assert guest.fractal_user_key.startswith("guest-guest_scope_a")

    user = resolve_memory_scope_from_user(_auth_user(7))
    assert user.scope_kind == "user"
    assert user.user_id == "7"
    assert user.context_key == "user:7"
    assert user.fractal_user_key == "user-7"


def test_guest_a_cannot_read_guest_b_image_context():
    clear_image_context_store()
    scope_a = resolve_memory_scope_from_user(_guest_user("guest_iso_a"))
    scope_b = resolve_memory_scope_from_user(_guest_user("guest_iso_b"))
    ctx = build_last_image_context(
        filename="a.png",
        mime_type="image/png",
        description="Secret A",
        detected_elements=["x"],
        media_id="img_guest_a_only",
    )
    set_last_image_context_scoped(scope_a, ctx)

    assert get_last_image_context(scope_a.context_key) is not None
    assert get_last_image_context(scope_b.context_key) is None
    assert get_last_image_context_for_user(_guest_user("guest_iso_b")) is None


def test_user_a_cannot_read_user_b_image_context():
    clear_image_context_store()
    scope_a = resolve_memory_scope_from_user(_auth_user(101))
    scope_b = resolve_memory_scope_from_user(_auth_user(202))
    ctx = build_last_image_context(
        filename="u.png",
        mime_type="image/png",
        description="User 101 secret",
        detected_elements=["y"],
        media_id="img_user_101",
    )
    set_last_image_context_scoped(scope_a, ctx)

    assert get_last_image_context(scope_a.context_key) is not None
    assert get_last_image_context(scope_b.context_key) is None


def test_cross_scope_write_blocked():
    clear_image_context_store()
    scope_a = resolve_memory_scope_from_user(_guest_user("guest_write_a"))
    scope_b_key = resolve_memory_scope_from_user(_guest_user("guest_write_b")).context_key
    ctx = build_last_image_context(
        filename="x.png",
        mime_type="image/png",
        description="blocked",
        detected_elements=[],
    )
    with pytest.raises(MemoryScopeError, match="cross-scope"):
        assert_scope_allows_context_key(scope_a, scope_b_key)


def test_media_id_from_other_scope_does_not_inject_context():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers_a = _guest_headers(client)

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS):
        intake = _post_intake(client, headers_a, "shot.png", PNG_MAGIC + b"\x00" * 8, "image/png")
    assert intake.status_code == 200
    foreign_media_id = intake.json()["media_id"]

    guest_b = _guest_user(headers_a["X-Guest-Session"] + "_other", ip="10.0.0.9")
    # Different guest session — must not see A's context even with A's media_id
    bundle = assemble_chat_generation_inputs(
        ChatRequest(message="Que vois-tu ?", media_id=foreign_media_id),
        user=guest_b,
        persist_memory_side_effects=False,
    )
    assert bundle["image_context_injected"] is False


def test_media_id_matches_own_scope_injects_context():
    clear_image_context_store()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)

    with patch("app.api.files_intake.analyze_image_bytes", return_value=_MOCK_ANALYSIS):
        intake = _post_intake(client, headers, "mine.png", PNG_MAGIC + b"\x00" * 8, "image/png")
    media_id = intake.json()["media_id"]

    guest = _guest_user(headers["X-Guest-Session"])
    bundle = assemble_chat_generation_inputs(
        ChatRequest(message="Décris cette image", media_id=media_id),
        user=guest,
        persist_memory_side_effects=False,
    )
    assert bundle["image_context_injected"] is True
    assert media_id in bundle["user_message"]


def test_last_image_context_stays_on_correct_scope_after_second_upload():
    clear_image_context_store()
    scope_a = resolve_memory_scope_from_user(_guest_user("guest_replace_a"))
    scope_b = resolve_memory_scope_from_user(_guest_user("guest_replace_b"))

    ctx_a = build_last_image_context(
        filename="a.png",
        mime_type="image/png",
        description="First A",
        detected_elements=[],
        media_id="img_a_1",
    )
    ctx_b = build_last_image_context(
        filename="b.png",
        mime_type="image/png",
        description="Only B",
        detected_elements=[],
        media_id="img_b_1",
    )
    set_last_image_context_scoped(scope_a, ctx_a)
    set_last_image_context_scoped(scope_b, ctx_b)

    loaded_a = get_last_image_context_for_user(_guest_user("guest_replace_a"))
    loaded_b = get_last_image_context_for_user(_guest_user("guest_replace_b"))
    assert loaded_a is not None and loaded_a.media_id == "img_a_1"
    assert loaded_b is not None and loaded_b.media_id == "img_b_1"


def test_media_id_allowed_for_scope_blocks_mismatch():
    scope = resolve_memory_scope_from_user(_guest_user("guest_mid"))
    assert media_id_allowed_for_scope(scope, "img_wrong", "img_correct") is False
    assert media_id_allowed_for_scope(scope, "img_correct", "img_correct") is True
    assert media_id_allowed_for_scope(scope, "", "img_correct") is True


def test_scope_allows_context_key_only_exact_match():
    scope = memory_scope_from_user(_auth_user(5))
    assert scope_allows_context_key(scope, "user:5") is True
    assert scope_allows_context_key(scope, "user:6") is False


def test_memory_scope_module_exports_logging_helpers():
    from app.memory import memory_scope as ms

    assert hasattr(ms, "log_memory_scope_resolved")
    assert hasattr(ms, "log_memory_read_scope")
    assert hasattr(ms, "log_memory_write_scope")
    assert hasattr(ms, "log_memory_cross_scope_blocked")
