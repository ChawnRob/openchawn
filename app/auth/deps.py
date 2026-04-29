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
