"""Obsidian connector — uri_handoff, local_rest, disabled."""

from __future__ import annotations

import os
from typing import Any, Literal

from app.integrations.obsidian.local_rest import ObsidianLocalRestError, write_note_via_local_rest
from app.integrations.obsidian.markdown_builder import (
    build_chat_note_markdown,
    derive_note_title,
    normalize_folder,
)
from app.integrations.obsidian.uri_handoff import build_uri_handoff

ObsidianSyncMode = Literal["uri_handoff", "local_rest", "disabled"]


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def resolve_obsidian_sync_mode() -> ObsidianSyncMode:
    explicit = (os.getenv("OBSIDIAN_SYNC_MODE") or "").strip().lower()
    if explicit in ("uri_handoff", "local_rest", "disabled"):
        return explicit  # type: ignore[return-value]

    if not _env_bool("OBSIDIAN_ENABLED", default=True):
        return "disabled"

    legacy_mode = (os.getenv("OBSIDIAN_MODE") or "uri").strip().lower()
    if _env_bool("OBSIDIAN_SYNC_ENABLED", default=False) and legacy_mode in ("local_rest", "rest"):
        return "local_rest"
    if legacy_mode in ("uri", "uri_handoff"):
        return "uri_handoff"
    if legacy_mode == "disabled":
        return "disabled"
    return "uri_handoff"


def _default_vault() -> str:
    return (
        (os.getenv("OBSIDIAN_DEFAULT_VAULT") or os.getenv("OBSIDIAN_VAULT_NAME") or "OpenChawn").strip()
        or "OpenChawn"
    )


def _default_folder() -> str:
    return (os.getenv("OBSIDIAN_DEFAULT_FOLDER") or "COCO").strip() or "COCO"


def _local_rest_configured() -> bool:
    return bool((os.getenv("OBSIDIAN_LOCAL_REST_URL") or "").strip()) and bool(
        (os.getenv("OBSIDIAN_LOCAL_REST_TOKEN") or "").strip()
    )


def get_obsidian_connector_status() -> dict[str, Any]:
    mode = resolve_obsidian_sync_mode()
    vault = _default_vault()
    folder = _default_folder()
    local_rest_ready = mode == "local_rest" and _local_rest_configured()
    enabled = mode != "disabled"
    return {
        "mode": mode,
        "enabled": enabled,
        "configured": enabled and (mode == "uri_handoff" or local_rest_ready),
        "vault_name": vault,
        "default_folder": folder,
        "local_rest_configured": local_rest_ready,
        "uri_open_available": enabled and mode in ("uri_handoff", "local_rest"),
        "can_write_directly": local_rest_ready,
    }


def create_obsidian_note(
    *,
    title: str = "",
    markdown: str = "",
    folder: str = "",
    source: str = "chat",
    user_text: str = "",
    assistant_text: str = "",
) -> dict[str, Any]:
    status = get_obsidian_connector_status()
    mode = status["mode"]
    folder_norm = normalize_folder(folder or status["default_folder"])
    vault = status["vault_name"]

    note_title = (title or "").strip() or derive_note_title(user_text or markdown[:80])
    body = (markdown or "").strip()
    if not body:
        body = build_chat_note_markdown(
            title=note_title,
            user_text=user_text,
            assistant_text=assistant_text,
            source=source,
        )

    if mode == "disabled":
        return {
            "ok": False,
            "mode": "disabled",
            "error": "Obsidian connector is not configured",
        }

    if mode == "local_rest":
        if not _local_rest_configured():
            handoff = build_uri_handoff(title=note_title, markdown=body, folder=folder_norm, vault=vault)
            return {
                "ok": True,
                "mode": "uri_handoff",
                "note_path": handoff["note_path"],
                "uri": handoff["uri"],
                "markdown": handoff["markdown"],
                "fallback": True,
                "error": "local_rest_not_configured",
            }
        try:
            result = write_note_via_local_rest(
                base_url=os.environ["OBSIDIAN_LOCAL_REST_URL"],
                token=os.environ["OBSIDIAN_LOCAL_REST_TOKEN"],
                title=note_title,
                markdown=body,
                folder=folder_norm,
            )
            return {
                "ok": True,
                "mode": "local_rest",
                "note_path": result["note_path"],
                "markdown": body,
            }
        except ObsidianLocalRestError as exc:
            handoff = build_uri_handoff(title=note_title, markdown=body, folder=folder_norm, vault=vault)
            return {
                "ok": True,
                "mode": "uri_handoff",
                "note_path": handoff["note_path"],
                "uri": handoff["uri"],
                "markdown": handoff["markdown"],
                "fallback": True,
                "error": str(exc),
            }

    handoff = build_uri_handoff(title=note_title, markdown=body, folder=folder_norm, vault=vault)
    return {
        "ok": True,
        "mode": "uri_handoff",
        "note_path": handoff["note_path"],
        "uri": handoff["uri"],
        "markdown": handoff["markdown"],
    }
