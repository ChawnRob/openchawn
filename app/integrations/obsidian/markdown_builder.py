"""Markdown note builder for Obsidian export."""

from __future__ import annotations

import re
from datetime import datetime, timezone


def _slugify(text: str, *, max_len: int = 40) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower())
    t = re.sub(r"-+", "-", t).strip("-")
    return t[:max_len] or "note"


def derive_note_title(user_text: str, *, created_at: str | None = None) -> str:
    stamp = (created_at or datetime.now(timezone.utc).isoformat())[:10]
    slug = _slugify(re.sub(r"\bobsidian\b", " ", user_text, flags=re.I))
    return f"COCO-{stamp}-{slug}" if slug else f"COCO-{stamp}"


def build_chat_note_markdown(
    *,
    title: str,
    user_text: str,
    assistant_text: str = "",
    source: str = "chat",
    created_at: str | None = None,
) -> str:
    created = created_at or datetime.now(timezone.utc).isoformat()
    user_body = (user_text or "").strip() or "_Aucune demande._"
    assistant_body = (assistant_text or "").strip() or "_Aucune réponse disponible pour cette demande._"
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- **Date:** {created}",
            f"- **Source:** {source} / COCO / OpenChawn",
            "",
            "## Demande utilisateur",
            "",
            user_body,
            "",
            "## Réponse COCO",
            "",
            assistant_body,
            "",
        ]
    )


def normalize_folder(folder: str) -> str:
    f = str(folder or "COCO").strip().strip("/")
    return f or "COCO"


def note_path_for_folder(folder: str, title: str) -> str:
    folder_norm = normalize_folder(folder)
    safe_title = str(title or "note").strip()
    if not safe_title.lower().endswith(".md"):
        safe_title = f"{safe_title}.md"
    safe_title = safe_title.replace("\\", "/").split("/")[-1]
    return f"{folder_norm}/{safe_title}"
