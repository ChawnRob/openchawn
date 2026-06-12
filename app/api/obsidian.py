"""Obsidian integration API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.integrations.obsidian.connector import create_obsidian_note, get_obsidian_connector_status

router = APIRouter(tags=["openchawn-obsidian"])


class ObsidianNoteRequest(BaseModel):
    title: str = ""
    markdown: str = ""
    folder: str = Field(default="COCO/", description="Vault folder for the note")
    source: str = "chat"
    user_text: str = ""
    assistant_text: str = ""


class ObsidianNoteResponse(BaseModel):
    ok: bool
    mode: str
    note_path: str | None = None
    uri: str | None = None
    markdown: str | None = None
    fallback: bool = False
    error: str | None = None


@router.post("/api/integrations/obsidian/notes", response_model=ObsidianNoteResponse)
def post_obsidian_note(req: ObsidianNoteRequest) -> dict[str, Any]:
    result = create_obsidian_note(
        title=req.title,
        markdown=req.markdown,
        folder=req.folder,
        source=req.source,
        user_text=req.user_text,
        assistant_text=req.assistant_text,
    )
    return result


@router.get("/api/integrations/obsidian/status")
def obsidian_integration_status() -> dict[str, Any]:
    return get_obsidian_connector_status()
