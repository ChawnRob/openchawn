"""
Jeton Bearer owner (OPENCHAWN_OWNER_TOKEN) — comparaison en temps constant.
Aucune journalisation ni exposition du secret.
"""

from __future__ import annotations

import secrets


def bearer_matches_configured_owner_token(provided: str | None, configured: str | None) -> bool:
    p = (provided or "").strip()
    e = (configured or "").strip()
    if not p or not e:
        return False
    try:
        if len(p) != len(e):
            return False
        return secrets.compare_digest(p.encode("utf-8"), e.encode("utf-8"))
    except Exception:
        return False


def owner_principal(ip: str) -> dict:
    """Identité applicative locale — aucun utilisateur DB."""
    return {
        "id": "owner-robert",
        "email": "",
        "display_name": "Robert",
        "business_type": "owner",
        "is_active": True,
        "is_guest": False,
        "is_owner": True,
        "user_role": "owner",
        "guest_session_id": "",
        "ip": ip,
    }
