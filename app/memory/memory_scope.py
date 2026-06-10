"""
Central memory scope resolution for COCO / OpenChawn.

Every durable or session-scoped memory write must carry a resolved scope with
either ``user_id`` (authenticated) or ``guest_session_id`` (guest).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Request

logger = logging.getLogger("openchawn.memory.scope")


class MemoryScopeError(ValueError):
    """Raised when a memory operation lacks a valid user/guest scope."""


@dataclass(frozen=True)
class MemoryScope:
    """Resolved isolation boundary for memory reads and writes."""

    scope_kind: str  # guest | user | owner | anon
    context_key: str  # guest:{id}, user:{id}, owner:{ip}, anon:{ip}
    fractal_user_key: str  # guest-{sid[:28]}, user-{id}, user-owner-robert
    is_guest: bool
    is_owner: bool
    user_id: str | None = None
    guest_session_id: str | None = None
    conversation_id: str | None = None
    ip: str = "unknown"

    def has_required_actor_key(self) -> bool:
        if self.is_guest:
            return bool((self.guest_session_id or "").strip())
        if self.scope_kind == "user":
            return self.user_id is not None and str(self.user_id).strip() != ""
        if self.is_owner:
            return True
        return bool((self.ip or "").strip() and self.ip != "unknown")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _conversation_id_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    for header in ("X-Conversation-Id", "X-OpenChawn-Conversation-Id"):
        value = (request.headers.get(header) or "").strip()
        if value:
            return value[:128]
    return None


def resolve_memory_scope_from_user(
    user: dict[str, Any],
    *,
    request: Request | None = None,
    conversation_id: str | None = None,
) -> MemoryScope:
    """Build a memory scope from an auth principal dict (guest, user, or owner)."""
    ip = str(user.get("ip") or (_client_ip(request) if request else "unknown"))
    conv_id = (conversation_id or "").strip() or _conversation_id_from_request(request)

    if user.get("is_guest"):
        guest_sid = str(user.get("guest_session_id") or "").strip()
        context_key = f"guest:{guest_sid}" if guest_sid else f"guest-ip:{ip}"
        fractal_key = f"guest-{guest_sid[:28]}" if guest_sid else f"guest-ip-{ip[:28]}"
        scope = MemoryScope(
            scope_kind="guest",
            context_key=context_key,
            fractal_user_key=fractal_key,
            is_guest=True,
            is_owner=False,
            guest_session_id=guest_sid or None,
            conversation_id=conv_id,
            ip=ip,
        )
    elif user.get("is_owner") or user.get("user_role") == "owner":
        scope = MemoryScope(
            scope_kind="owner",
            context_key=f"owner:{ip}",
            fractal_user_key="user-owner-robert",
            is_guest=False,
            is_owner=True,
            user_id=str(user.get("id") or "owner-robert"),
            conversation_id=conv_id,
            ip=ip,
        )
    elif user.get("id") is not None:
        uid = str(user["id"])
        scope = MemoryScope(
            scope_kind="user",
            context_key=f"user:{uid}",
            fractal_user_key=f"user-{uid}",
            is_guest=False,
            is_owner=False,
            user_id=uid,
            conversation_id=conv_id,
            ip=ip,
        )
    else:
        scope = MemoryScope(
            scope_kind="anon",
            context_key=f"anon:{ip}",
            fractal_user_key=f"anon-{ip[:28]}",
            is_guest=False,
            is_owner=False,
            conversation_id=conv_id,
            ip=ip,
        )

    assert_memory_scope_valid(scope)
    return scope


def resolve_memory_scope(request: Request) -> MemoryScope:
    """
    Resolve memory scope from an HTTP request (auth principal + optional conversation id).

    Uses the same principal resolution as ``get_current_user_or_guest``.
    """
    from app.auth.deps import get_current_user_or_guest

    user = get_current_user_or_guest(request)
    scope = resolve_memory_scope_from_user(user, request=request)
    log_memory_scope_resolved(scope, source="http_request")
    return scope


def assert_memory_scope_valid(scope: MemoryScope) -> None:
    """Every memory write/read must have user_id or guest_session_id (or owner scope)."""
    if scope.has_required_actor_key():
        return
    raise MemoryScopeError(
        "memory scope invalid: authenticated user_id or guest_session_id required"
    )


def scope_allows_context_key(scope: MemoryScope, context_key: str) -> bool:
    """Return True when the requested storage key matches the resolved scope."""
    expected = (scope.context_key or "").strip()
    requested = (context_key or "").strip()
    if not expected or not requested:
        return False
    return expected == requested


def assert_scope_allows_context_key(scope: MemoryScope, context_key: str) -> None:
    if scope_allows_context_key(scope, context_key):
        return
    log_memory_cross_scope_blocked(scope, context_key, operation="access")
    raise MemoryScopeError("memory cross-scope access blocked")


def scope_key_for_log(scope: MemoryScope) -> dict[str, str]:
    """Non-sensitive fields safe for structured logs."""
    out: dict[str, str] = {
        "scope_kind": scope.scope_kind,
        "context_key": _redact_context_key(scope.context_key),
        "fractal_user_key": _redact_fractal_key(scope.fractal_user_key),
        "is_guest": str(scope.is_guest).lower(),
        "is_owner": str(scope.is_owner).lower(),
    }
    if scope.user_id:
        out["user_id"] = scope.user_id
    if scope.guest_session_id:
        out["guest_session_id"] = _redact_guest_session(scope.guest_session_id)
    if scope.conversation_id:
        out["conversation_id"] = scope.conversation_id[:12] + "…" if len(scope.conversation_id) > 12 else scope.conversation_id
    return out


def _redact_guest_session(session_id: str) -> str:
    sid = (session_id or "").strip()
    if len(sid) <= 12:
        return sid
    return f"{sid[:12]}…"


def _redact_context_key(context_key: str) -> str:
    key = (context_key or "").strip()
    if key.startswith("guest:") and len(key) > 18:
        return f"guest:{key[6:18]}…"
    return key


def _redact_fractal_key(fractal_key: str) -> str:
    key = (fractal_key or "").strip()
    if key.startswith("guest-") and len(key) > 16:
        return f"guest-{key[6:16]}…"
    return key


def log_memory_scope_resolved(scope: MemoryScope, *, source: str) -> None:
    payload = scope_key_for_log(scope)
    payload["source"] = source
    logger.info("memory_scope_resolved | %s", " | ".join(f"{k}={v}" for k, v in payload.items()))


def log_memory_read_scope(scope: MemoryScope, store: str, *, context_key: str | None = None) -> None:
    payload = scope_key_for_log(scope)
    payload["store"] = store
    if context_key:
        payload["context_key"] = _redact_context_key(context_key)
    logger.info("memory_read_scope | %s", " | ".join(f"{k}={v}" for k, v in payload.items()))


def log_memory_write_scope(scope: MemoryScope, store: str, *, context_key: str | None = None) -> None:
    payload = scope_key_for_log(scope)
    payload["store"] = store
    if context_key:
        payload["context_key"] = _redact_context_key(context_key)
    logger.info("memory_write_scope | %s", " | ".join(f"{k}={v}" for k, v in payload.items()))


def log_memory_cross_scope_blocked(
    scope: MemoryScope,
    attempted_key: str,
    *,
    operation: str,
) -> None:
    payload = scope_key_for_log(scope)
    payload["operation"] = operation
    payload["attempted_key"] = _redact_context_key(attempted_key)
    logger.warning(
        "memory_cross_scope_blocked | %s",
        " | ".join(f"{k}={v}" for k, v in payload.items()),
    )


def media_id_allowed_for_scope(scope: MemoryScope, media_id: str, stored_media_id: str | None) -> bool:
    """
    A client-supplied media_id must match the scope's stored context when provided.
    """
    mid = (media_id or "").strip()
    stored = (stored_media_id or "").strip()
    if not mid:
        return True
    if not stored:
        return False
    if mid == stored:
        return True
    log_memory_cross_scope_blocked(scope, f"media_id:{mid[:16]}…", operation="media_id_mismatch")
    return False
