"""Privacy-safe auth event logging."""

from __future__ import annotations

import hashlib


def privacy_user_log_ref(user_id: int | str, email: str = "") -> str:
    """Return a log-safe user reference without plain email."""
    uid = str(user_id or "").strip() or "unknown"
    em = (email or "").strip().lower()
    if em:
        digest = hashlib.sha256(em.encode("utf-8")).hexdigest()[:10]
        return f"user_id={uid} email_hash={digest}"
    return f"user_id={uid}"
