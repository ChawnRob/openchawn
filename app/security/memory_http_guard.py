"""HTTP guard for /memory/* routes (P0)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import HTTPException
from starlette.responses import JSONResponse
from app.auth.deps import get_current_user
from app.config import IS_PROD
from app.security.memory_access import memory_account_key

# Production: only these paths may execute (scoped per-user reads).
_PROD_ALLOWED_EXACT = {
    "/memory/recent",
    "/memory/concepts",
    "/memory/top",
    "/memory/system",
    "/memory/projects",
    "/memory/user",
    "/memory/session",
    "/memory/archive",
    "/memory/importance/top",
    "/memory/semantic/search",
}

_PROD_ALLOWED_PREFIXES = (
    "/memory/trace/",
    "/memory/importance/explain/",
    "/memory/graph/related/",
    "/memory/graph/explain/",
    "/memory/compression/",
)


def _memory_path_allowed_in_prod(path: str, method: str) -> bool:
    if path in _PROD_ALLOWED_EXACT:
        return True
    if method == "POST" and path == "/memory/search":
        return True
    return any(path.startswith(prefix) for prefix in _PROD_ALLOWED_PREFIXES)


class MemoryHttpGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path != "/memory" and not path.startswith("/memory/"):
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)

        try:
            user = get_current_user(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        request.state.memory_user = user
        request.state.memory_user_key = memory_account_key(user)

        if IS_PROD and not _memory_path_allowed_in_prod(path, request.method):
            return JSONResponse(
                status_code=403,
                content={"detail": "Endpoint mémoire global désactivé en production"},
            )

        if path == "/memory":
            return JSONResponse(
                status_code=403,
                content={"detail": "Endpoint mémoire global désactivé en production"},
            )

        return await call_next(request)
