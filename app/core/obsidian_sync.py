"""Optional Obsidian Markdown sync — thin facade over app.integrations.obsidian."""

from __future__ import annotations

from typing import Any

from app.integrations.obsidian.connector import get_obsidian_connector_status, resolve_obsidian_sync_mode

OBSIDIAN_SYNC_MARKER = "obsidian_sync_runtime_v2"


def get_obsidian_sync_status() -> dict[str, Any]:
    """Safe public status — no API token, no local REST URL."""
    st = get_obsidian_connector_status()
    mode = st["mode"]
    legacy_mode = "uri" if mode == "uri_handoff" else mode
    return {
        "marker": OBSIDIAN_SYNC_MARKER,
        "enabled": st["enabled"],
        "mode": legacy_mode,
        "sync_mode": mode,
        "vault_name": st["vault_name"],
        "default_folder": st["default_folder"],
        "sync_enabled": mode == "local_rest" and st.get("local_rest_configured"),
        "configured": st["configured"],
        "uri_open_available": st["uri_open_available"],
        "can_write_directly": st.get("can_write_directly", False),
    }


def build_obsidian_sync_context() -> str:
    """English system-prompt block for COCO (model answers in user language)."""
    st = get_obsidian_sync_status()
    mode = st["sync_mode"]
    if mode == "disabled" or not st["enabled"]:
        return (
            f"OBSIDIAN_SYNC_RUNTIME_MARKER: {OBSIDIAN_SYNC_MARKER}\n\n"
            "Obsidian optional Markdown export (separate from AFFiNE Second Brain):\n"
            "- Obsidian connector mode: disabled — Obsidian Sync is not configured.\n"
            "- If asked to connect, sync, or send to Obsidian, say the connector is not configured.\n"
            "- Never claim sync succeeded or that a note was written inside Obsidian.\n"
        )
    if mode == "local_rest" and st.get("can_write_directly"):
        return (
            f"OBSIDIAN_SYNC_RUNTIME_MARKER: {OBSIDIAN_SYNC_MARKER}\n\n"
            "Obsidian local REST mode (direct vault write when API succeeds):\n"
            f"- vault={st['vault_name']}; folder={st['default_folder']}.\n"
            "- COCO may create notes via POST /api/integrations/obsidian/notes when the user asks "
            "to note/save/sync content to Obsidian.\n"
            "- Only say « C'est noté dans Obsidian » or equivalent AFTER the connector API returns success.\n"
            "- If the API falls back to uri_handoff, use the Sync Obsidian button flow and do not claim write success.\n"
            "- Note intent examples: « note ça dans Obsidian », « synchronise ça dans Obsidian », "
            "« enregistre cette conversation dans Obsidian », « ajoute ce résumé à Obsidian ».\n"
        )
    return (
        f"OBSIDIAN_SYNC_RUNTIME_MARKER: {OBSIDIAN_SYNC_MARKER}\n\n"
        "Obsidian URI handoff mode (optional Markdown export — AFFiNE remains the primary Second Brain):\n"
        f"- vault={st['vault_name']}; folder={st['default_folder']}.\n"
        "- URI mode is a local device handoff (obsidian://new on user tap), not direct API read/write.\n"
        "- COCO prepares Markdown and the Sync Obsidian button triggers obsidian://new with encoded name/content.\n"
        "- Never claim sync succeeded before the user taps Sync Obsidian.\n"
        "- Do NOT deny Obsidian connectivity when uri_handoff is active.\n"
        "- Note intent examples: « note ça dans Obsidian », « synchronise ça dans Obsidian », "
        "« enregistre cette conversation dans Obsidian », « ajoute ce résumé à Obsidian ».\n"
    )


__all__ = [
    "OBSIDIAN_SYNC_MARKER",
    "build_obsidian_sync_context",
    "get_obsidian_sync_status",
    "resolve_obsidian_sync_mode",
]
