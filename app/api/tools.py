"""Tools API — runtime capability status."""

from __future__ import annotations

from fastapi import APIRouter

from app.tools.web_search import get_web_search_status

router = APIRouter(tags=["openchawn-tools"])


@router.get("/api/tools/status")
def tools_status():
    """Public safe status for OpenChawn runtime tools (no secrets)."""
    return {
        "web_search": get_web_search_status(),
    }
