"""Optional Obsidian Markdown sync — separate from AFFiNE Second Brain."""

from __future__ import annotations

import os
from typing import Any

OBSIDIAN_SYNC_MARKER = "obsidian_sync_runtime_v1"


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def get_obsidian_sync_status() -> dict[str, Any]:
    """Safe public status — no API token, no local REST URL."""
    enabled = _env_bool("OBSIDIAN_ENABLED", default=False)
    sync_enabled = _env_bool("OBSIDIAN_SYNC_ENABLED", default=False)
    mode = (os.getenv("OBSIDIAN_MODE") or "uri").strip() or "uri"
    vault_name = (os.getenv("OBSIDIAN_VAULT_NAME") or "OpenChawn").strip() or "OpenChawn"
    default_folder = (os.getenv("OBSIDIAN_DEFAULT_FOLDER") or "COCO").strip() or "COCO"
    return {
        "marker": OBSIDIAN_SYNC_MARKER,
        "enabled": enabled,
        "mode": mode,
        "vault_name": vault_name,
        "default_folder": default_folder,
        "sync_enabled": sync_enabled,
        "configured": enabled,
        "uri_open_available": enabled and mode == "uri",
    }
