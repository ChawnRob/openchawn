"""
Last image context per chat session (guest or authenticated).

Structured vision summary only — no durable file bytes.
Persisted via Postgres/SQLite when available (Railway multi-replica safe).
"""
from __future__ import annotations

import logging
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.auth.guest import get_guest_last_image_context, set_guest_last_image_context
from app.files_intake.image_context_persistence import (
    clear_image_context_memory_cache,
    clear_image_context_persistence,
    load_image_context,
    persist_image_context,
)
from app.memory.memory_scope import (
    MemoryScope,
    assert_scope_allows_context_key,
    log_memory_read_scope,
    log_memory_write_scope,
    media_id_allowed_for_scope,
    resolve_memory_scope_from_user,
)

# Re-export for tests simulating multi-worker RAM isolation.
__all__ = ["clear_image_context_memory_cache"]

logger = logging.getLogger("openchawn.files_intake.image_context")

_IMAGE_REF_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(image|photo|capture|screenshot|selfie)\b",
        r"\b(derni[eè]re|last|recent)\s+(image|photo|capture|fichier)\b",
        r"\b(pr[eé]c[eé]dente?|previous)\s+(image|photo|capture)\b",
        r"\b(image|photo)\s+(pr[eé]c[eé]dente?|envoy[eé]e?\s+pr[eé]c[eé]demment)\b",
        r"\b(image|photo)\s+que\s+je\s+viens\s+d['']envoyer\b",
        r"\b(celle|that)\s+(que\s+)?(j['']?ai\s+)?envoy[eé]e?\b",
        r"\b(celle|that)\s+envoy[eé]e?\s+avant\b",
        r"\bl['']?(image|photo)\s+pr[eé]c[eé]dente\b",
        r"\bla\s+(image|photo)\s+pr[eé]c[eé]dente\b",
        r"\bfichier\s+joint\b",
        r"\battached\s+file\b",
        r"\b(file|photo)\s+(i\s+)?(just\s+)?(sent|uploaded|shared)\b",
        r"\b(celle|that)\s+(que\s+)?(je\s+)?(viens\s+d[''])?envoy",
        r"\banalyse[- ]?(la|l['']|this|it|the\s+image)?\b",
        r"\banalyze\s+(it|this|the\s+image|the\s+photo)\b",
        r"\b(peux[- ]tu|can\s+you).{0,40}\b(image|photo)\b",
        r"\b(dis|tell|say).{0,30}\b(plus|more)\b.{0,40}\b(image|photo)\b",
        r"\b(en\s+savoir\s+plus|more\s+about).{0,40}\b(image|photo|picture)\b",
        r"\bl['']?(image|photo)\s+que\s+je\s+viens\s+d['']envoyer\b",
        r"\bla\s+(image|photo)\s+que\s+je\s+viens\s+d['']envoyer\b",
        r"\bd[eé]cris\b.{0,40}\b(l['']?)?(image|photo)\b",
        r"\bdescribe\b.{0,40}\b(the\s+)?(image|photo|picture)\b",
    )
)


@dataclass(frozen=True)
class LastImageContext:
    media_id: str
    filename: str
    mime_type: str
    description: str
    detected_elements: list[str]
    extracted_text: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_media_id() -> str:
    return f"img_{secrets.token_urlsafe(10)}"


def session_key_from_user(user: dict) -> str:
    """Session / image context key — aligned with ``MemoryScope.context_key``."""
    return resolve_memory_scope_from_user(user).context_key


def memory_scope_from_user(user: dict) -> MemoryScope:
    return resolve_memory_scope_from_user(user)


def context_key_for_log(context_key: str) -> str:
    key = (context_key or "").strip()
    if key.startswith("guest:"):
        sid = key[6:]
        if len(sid) > 12:
            return f"guest:{sid[:12]}…"
    return key


def _guest_session_id_from_key(context_key: str) -> str | None:
    if context_key.startswith("guest:"):
        sid = context_key[6:].strip()
        return sid or None
    return None


def _extract_text_hint(elements: list[str]) -> str | None:
    hints: list[str] = []
    for item in elements:
        s = (item or "").strip()
        if not s:
            continue
        if re.search(r"\b(texte|text|label|ocr|écrit|sign|caption|titre)\b", s, re.IGNORECASE):
            hints.append(s)
    return "; ".join(hints) if hints else None


def build_last_image_context(
    *,
    filename: str,
    mime_type: str,
    description: str,
    detected_elements: list[str],
    media_id: str | None = None,
) -> LastImageContext:
    return LastImageContext(
        media_id=media_id or new_media_id(),
        filename=filename,
        mime_type=mime_type,
        description=description,
        detected_elements=list(detected_elements or []),
        extracted_text=_extract_text_hint(detected_elements),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def set_last_image_context(session_key: str, ctx: LastImageContext) -> str:
    """Persist context; returns storage backend label."""
    if not session_key:
        return "ram"
    payload = ctx.to_dict()
    backend = persist_image_context(session_key, payload)
    guest_sid = _guest_session_id_from_key(session_key)
    if guest_sid:
        set_guest_last_image_context(guest_sid, payload)
    return backend


def set_last_image_context_scoped(scope: MemoryScope, ctx: LastImageContext) -> str:
    """Scoped write — context key must match resolved memory scope."""
    assert_scope_allows_context_key(scope, scope.context_key)
    log_memory_write_scope(scope, "last_image_context", context_key=scope.context_key)
    return set_last_image_context(scope.context_key, ctx)


def get_last_image_context(session_key: str) -> LastImageContext | None:
    raw = load_image_context(session_key)
    if not raw:
        guest_sid = _guest_session_id_from_key(session_key)
        if guest_sid:
            raw = get_guest_last_image_context(guest_sid)
    if not raw:
        return None
    return LastImageContext(**raw)


def get_last_image_context_scoped(scope: MemoryScope) -> LastImageContext | None:
    """Scoped read — only the resolved context_key is accessed."""
    log_memory_read_scope(scope, "last_image_context", context_key=scope.context_key)
    return get_last_image_context(scope.context_key)


def get_last_image_context_for_user(
    user: dict,
    *,
    media_id: str | None = None,
) -> LastImageContext | None:
    """Load image context for a principal; optional media_id must match stored value."""
    scope = resolve_memory_scope_from_user(user)
    ctx = get_last_image_context_scoped(scope)
    if ctx is None:
        return None
    if media_id and not media_id_allowed_for_scope(scope, media_id, ctx.media_id):
        return None
    return ctx


def clear_image_context_store() -> None:
    clear_image_context_memory_cache()
    clear_image_context_persistence()


def message_references_recent_image(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in _IMAGE_REF_PATTERNS)


def format_image_context_for_prompt(ctx: LastImageContext) -> str:
    elements = ", ".join(ctx.detected_elements) if ctx.detected_elements else "(aucun)"
    ocr = ctx.extracted_text or "(aucun texte extrait)"
    return (
        "── LAST IMAGE CONTEXT (session, structured vision summary) ──\n"
        f"media_id: {ctx.media_id}\n"
        f"filename: {ctx.filename}\n"
        f"mime_type: {ctx.mime_type}\n"
        f"uploaded_at: {ctx.created_at}\n"
        f"description: {ctx.description}\n"
        f"detected_elements: {elements}\n"
        f"extracted_text: {ocr}\n"
        "Instruction: The user refers to this recently uploaded image. "
        "Answer using this context. Do NOT claim you cannot see the image when this block is present."
    )
