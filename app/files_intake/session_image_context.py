"""
In-memory last image context per chat session (guest or authenticated).

Structured vision summary only — no durable file bytes.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

_IMAGE_REF_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(image|photo|capture|screenshot|selfie)\b",
        r"\b(derni[eè]re|last|recent)\s+(image|photo|capture|fichier)\b",
        r"\bfichier\s+joint\b",
        r"\battached\s+file\b",
        r"\b(file|photo)\s+(i\s+)?(just\s+)?(sent|uploaded|shared)\b",
        r"\b(celle|that)\s+(que\s+)?(je\s+)?(viens\s+d[''])?envoy",
        r"\banalyse[- ]?(la|l['']|this|it|the\s+image)?\b",
        r"\banalyze\s+(it|this|the\s+image|the\s+photo)\b",
        r"\b(peux[- ]tu|can\s+you).{0,40}\b(image|photo)\b",
        r"\b(dis|tell|say).{0,30}\b(plus|more)\b.{0,40}\b(image|photo)\b",
        r"\b(en\s+savoir\s+plus|more\s+about).{0,40}\b(image|photo|picture)\b",
    )
)

_store: dict[str, dict[str, Any]] = {}


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
    if user.get("is_guest"):
        sid = str(user.get("guest_session_id") or "").strip()
        return f"guest:{sid}" if sid else f"guest-ip:{user.get('ip', 'unknown')}"
    if user.get("id") is not None:
        return f"user:{user['id']}"
    if user.get("is_owner"):
        return f"owner:{user.get('ip', 'unknown')}"
    return f"anon:{user.get('ip', 'unknown')}"


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


def set_last_image_context(session_key: str, ctx: LastImageContext) -> None:
    if not session_key:
        return
    _store[session_key] = ctx.to_dict()


def get_last_image_context(session_key: str) -> LastImageContext | None:
    raw = _store.get(session_key)
    if not raw:
        return None
    return LastImageContext(**raw)


def clear_image_context_store() -> None:
    _store.clear()


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
