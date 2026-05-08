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
_last_chat_request_at: dict[str, float] = {}
_request_counts: dict[str, int] = defaultdict(int)

# Routes et leurs limites
_RATE_RULES: dict[str, int] = {
    "/chat": RATE_LIMIT_CHAT,
    "/api/chat": RATE_LIMIT_CHAT,
    "/register": RATE_LIMIT_AUTH,
    "/login": RATE_LIMIT_AUTH,
    "/guest/session": RATE_LIMIT_AUTH,
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        _request_counts[client_ip] += 1
        logger.info(
            f"request | ip={client_ip} | path={path} | count={_request_counts[client_ip]}"
        )

        # Chat guardrail: max 1 request per 2 seconds per IP (mounted paths share policy)
        if path in ("/chat", "/api/chat"):
            auth_header = (request.headers.get("Authorization", "") or "").strip()
            guest_session = (request.headers.get("X-Guest-Session", "") or "").strip()
            if guest_session:
                actor_key = f"{client_ip}:guest:{guest_session}"
            elif auth_header.startswith("Bearer "):
                actor_key = f"{client_ip}:auth:{auth_header[7:19]}"
            else:
                actor_key = client_ip
            now = time.time()
            last = _last_chat_request_at.get(actor_key, 0.0)
            if now - last < 2.0:
                logger.warning(
                    f"rate limit blocked | ip={client_ip} | path={path} | "
                    f"actor={actor_key[:48]} | delta={now - last:.3f}s"
                )
                return JSONResponse(status_code=429, content={"detail": "Too many requests"})
            _last_chat_request_at[actor_key] = now

        limit = _RATE_RULES.get(path)
        if limit:
            key = f"{client_ip}:{path}"
            if not _buckets[key].check(limit):
                logger.warning(
                    f"rate limit blocked | ip={client_ip} | path={path} | "
                    f"rule={limit}/60s"
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
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
