"""Obsidian Local REST API connector."""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.integrations.obsidian.markdown_builder import note_path_for_folder

logger = logging.getLogger("openchawn.obsidian.local_rest")


class ObsidianLocalRestError(RuntimeError):
    """Raised when Local REST write fails."""


def write_note_via_local_rest(
    *,
    base_url: str,
    token: str,
    title: str,
    markdown: str,
    folder: str,
    timeout_s: float = 12.0,
) -> dict[str, Any]:
    if not base_url or not str(base_url).strip():
        raise ObsidianLocalRestError("OBSIDIAN_LOCAL_REST_URL is not configured")
    if not token or not str(token).strip():
        raise ObsidianLocalRestError("OBSIDIAN_LOCAL_REST_TOKEN is not configured")

    note_path = note_path_for_folder(folder, title)
    url = f"{str(base_url).rstrip('/')}/vault/{note_path}"
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "text/markdown",
    }
    try:
        resp = requests.put(url, data=markdown.encode("utf-8"), headers=headers, timeout=timeout_s)
    except requests.RequestException as exc:
        raise ObsidianLocalRestError(f"Local REST request failed: {exc}") from exc

    if resp.status_code not in (200, 201, 204):
        detail = (resp.text or "").strip()[:240]
        raise ObsidianLocalRestError(
            f"Local REST write failed: HTTP {resp.status_code}" + (f" — {detail}" if detail else "")
        )

    logger.info("obsidian local_rest write ok path=%s status=%s", note_path, resp.status_code)
    return {"note_path": note_path, "status_code": resp.status_code}
