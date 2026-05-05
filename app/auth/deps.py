"""
Dépendances FastAPI pour l'authentification.
"""
from fastapi import Request, HTTPException
from app.auth.security import verify_token
from app.auth.database import get_user_by_id


def get_current_user(request: Request) -> dict:
    """Extrait et valide le user depuis le header Authorization: Bearer <token>."""
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
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
    Tente l'auth JWT classique. Si absent/invalide, cherche un header
    X-Guest-Session pour identifier un visiteur anonyme.
    Retourne un dict avec is_guest=True/False.
    """
    auth_header = request.headers.get("Authorization", "")

    # ── Authenticated user ──
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_token(token)
        if payload:
            user = get_user_by_id(int(payload["sub"]))
            if user and user["is_active"]:
                return {**user, "is_guest": False}

    # ── Guest session ──
    guest_session_id = request.headers.get("X-Guest-Session", "").strip()
    if guest_session_id:
        client_ip = request.client.host if request.client else "unknown"
        return {
            "is_guest": True,
            "guest_session_id": guest_session_id,
            "ip": client_ip,
        }

    raise HTTPException(
        status_code=401,
        detail="Token ou session guest manquant",
    )
