"""
Dépendances FastAPI pour l'authentification.
"""
from fastapi import Request, HTTPException

from app.auth.database import get_user_by_id
from app.auth.owner_access import bearer_matches_configured_owner_token, owner_principal
from app.auth.security import verify_token
from app.settings import get_settings


def get_current_user(request: Request) -> dict:
    """Extrait et valide le user depuis le header Authorization: Bearer <token>."""
    auth_header = (request.headers.get("Authorization") or "").strip()

    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")

    token = auth_header[7:]
    payload = verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")

    user = get_user_by_id(int(payload["sub"]))
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Compte désactivé")

    return user


def get_current_user_or_guest(request: Request) -> dict:
    """
    Ordre :
      - Bearer OPENCHAWN_OWNER_TOKEN (prioritaire, ne transite pas en log) ;
      - JWT compte ;
      - X-Guest-Session invité.

    Retourne un dict avec is_guest=True/False ; owner : is_owner + user_role.
    """
    auth_header = (request.headers.get("Authorization") or "").strip()
    client_ip = request.client.host if request.client else "unknown"

    bearer = ""
    lower = auth_header.lower()
    if lower.startswith("bearer "):
        bearer = auth_header[7:].strip()

    owner_cfg = get_settings().openchawn_owner_token
    if bearer and bearer_matches_configured_owner_token(bearer, owner_cfg):
        return owner_principal(client_ip)

    # ── Authenticated user (JWT — ne doit jamais recevoir une valeur journalisée) ──
    if lower.startswith("bearer "):
        token = auth_header[7:]
        payload = verify_token(token)
        if payload:
            user = get_user_by_id(int(payload["sub"]))
            if user and user["is_active"]:
                return {**user, "is_guest": False, "user_role": "user"}

    # ── Guest session ──
    guest_session_id = request.headers.get("X-Guest-Session", "").strip()
    if guest_session_id:
        return {
            "is_guest": True,
            "user_role": "guest",
            "guest_session_id": guest_session_id,
            "ip": client_ip,
        }

    raise HTTPException(
        status_code=401,
        detail="Token ou session guest manquant",
    )
