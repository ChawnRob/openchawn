"""
Middlewares : rate limiting + error handler + security headers.
Zéro dépendance externe.
"""
import time
import logging
from collections import defaultdict
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import RATE_LIMIT_CHAT, RATE_LIMIT_AUTH, IS_PROD

logger = logging.getLogger("openchawn.middleware")


# ── Rate Limiter (en mémoire, par IP) ────────────────────

class _RateBucket:
    __slots__ = ("timestamps",)

    def __init__(self):
        self.timestamps: list[float] = []

    def check(self, limit: int, window: int = 60) -> bool:
        now = time.time()
        cutoff = now - window
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        if len(self.timestamps) >= limit:
            return False
        self.timestamps.append(now)
        return True


_buckets: dict[str, _RateBucket] = defaultdict(_RateBucket)

# Routes et leurs limites
_RATE_RULES: dict[str, int] = {
    "/chat": RATE_LIMIT_CHAT,
    "/register": RATE_LIMIT_AUTH,
    "/login": RATE_LIMIT_AUTH,
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        limit = _RATE_RULES.get(path)
        if limit:
            client_ip = request.client.host if request.client else "unknown"
            key = f"{client_ip}:{path}"
            if not _buckets[key].check(limit):
                logger.warning(f"Rate limit: {client_ip} on {path}")
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Trop de requêtes. Réessayez dans un moment."},
                )
        return await call_next(request)


# ── Security Headers ─────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if IS_PROD:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


# ── Error Handler global ─────────────────────────────────

async def global_error_handler(request: Request, exc: Exception):
    """Masque les stacktraces en prod."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    logger.error(f"Erreur non gérée: {type(exc).__name__}: {exc}", exc_info=not IS_PROD)

    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du serveur." if IS_PROD else str(exc)},
    )
