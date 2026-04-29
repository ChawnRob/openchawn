"""
Sécurité : hash passwords + JWT tokens.
Zéro dépendance externe — stdlib uniquement (hashlib + hmac).
"""
import hashlib
import hmac
import json
import os
import time
import base64
from app.config import SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_HOURS


# ── Password hashing (PBKDF2-SHA256, 600k iterations) ────

def hash_password(password: str) -> str:
    """Hash un mot de passe avec salt aléatoire. Retourne salt:hash en hex."""
    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe contre le hash stocké."""
    try:
        salt_hex, hash_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ── JWT tokens (HMAC-SHA256, implémentation stdlib) ──────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def create_token(user_id: int, email: str) -> str:
    """Crée un JWT signé HMAC-SHA256."""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_data = {
        "sub": str(user_id),
        "email": email,
        "exp": int(time.time()) + JWT_EXPIRE_HOURS * 3600,
        "iat": int(time.time()),
    }
    payload = _b64url_encode(json.dumps(payload_data).encode())
    signature = hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    sig = _b64url_encode(signature)
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> dict | None:
    """Vérifie et décode un JWT. Retourne le payload ou None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header, payload, sig = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_data = json.loads(_b64url_decode(payload))

        if payload_data.get("exp", 0) < time.time():
            return None

        return payload_data
    except Exception:
        return None
