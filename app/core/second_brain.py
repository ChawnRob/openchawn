"""COCO Second Brain runtime — user-owned AFFiNE workspace (no default OpenChawn document storage)."""

from __future__ import annotations

import os
from typing import Any

# Marqueur test / audit : grep second_brain_runtime_v1
SECOND_BRAIN_MARKER = "second_brain_runtime_v1"

SUPPORTED_ACTIONS_CURRENT = (
    "open_affine",
    "prepare_note",
    "prepare_summary",
    "prepare_project_page",
)

SUPPORTED_ACTIONS_FUTURE = (
    "read_workspace",
    "write_page",
    "search_documents",
    "create_canvas",
    "index_metadata",
)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def is_affine_api_sync_active() -> bool:
    """Deep AFFiNE API sync — off unless explicitly enabled and verified."""
    return _env_bool("OPENCHAWN_AFFINE_API_SYNC_ACTIVE", default=False)


def is_affine_open_configured() -> bool:
    """
    User can open AFFiNE from COCO (UI handler + optional operator URLs).
    Does not expose URL values — only whether open flow is available.
    """
    if _env_bool("OPENCHAWN_AFFINE_OPEN_DISABLED", default=False):
        return False
    return True


def get_second_brain_status() -> dict[str, Any]:
    """Safe public status — no secrets, no private URLs."""
    return {
        "provider": "AFFiNE",
        "mode": "local-first",
        "ownership": "user-owned",
        "open_action_configured": is_affine_open_configured(),
        "api_sync_active": is_affine_api_sync_active(),
        "openchawn_document_storage_default": False,
        "consent_required_for_sync": True,
        "supported_actions_current": list(SUPPORTED_ACTIONS_CURRENT),
        "supported_actions_future": list(SUPPORTED_ACTIONS_FUTURE),
    }


def build_second_brain_context() -> str:
    """English system-prompt block for COCO (model answers in user language)."""
    st = get_second_brain_status()
    sync_line = (
        "Deep AFFiNE API sync is ACTIVE in this deployment — only use read/write/search "
        "capabilities if the user has given explicit consent and the action is supported."
        if st["api_sync_active"]
        else (
            "Deep AFFiNE API sync is NOT active in this deployment. Do not claim you can read, "
            "write, search, or index the user's AFFiNE workspace via API. You can open AFFiNE "
            "and help prepare content (notes, summaries, project pages) for the user to place "
            "in their workspace."
        )
    )
    return (
        f"SECOND_BRAIN_RUNTIME_MARKER: {SECOND_BRAIN_MARKER}\n\n"
        "Second Brain (user-owned AFFiNE workspace):\n"
        f"- Provider: {st['provider']}; mode: {st['mode']}; ownership: {st['ownership']}.\n"
        "- AFFiNE is the user's Second Brain. Prefer local-first / desktop workspace when the user controls data on their machine.\n"
        "- OpenChawn does NOT store user documents by default (openchawn_document_storage_default=false).\n"
        f"- Open AFFiNE from COCO: {'available' if st['open_action_configured'] else 'not configured'}.\n"
        f"- {sync_line}\n"
        "- Future workspace read/write/indexing requires explicit user consent (consent_required_for_sync=true).\n"
        "- Current supported actions: "
        + ", ".join(st["supported_actions_current"])
        + ".\n"
        "- Not available until API sync is verified: "
        + ", ".join(st["supported_actions_future"])
        + ".\n"
        "- When asked in French whether you can manage their Second Brain (e.g. « Est-ce que tu peux gérer mon Second Brain ? »), "
        "answer in French and include substance equivalent to:\n"
        "  • Yes — help structure notes, summaries, and organization for their AFFiNE Second Brain.\n"
        "  • Today — open AFFiNE and prepare content for them to save in their workspace.\n"
        "  • Deep API connection is not active yet unless api_sync_active is true.\n"
        "  • Their documents stay in their AFFiNE environment, not stored by OpenChawn by default.\n"
        "- Never say: « AFFiNE is connected », « OpenChawn stores your documents », or « Memory sync is active » unless api_sync_active is true and consent is documented."
    )
