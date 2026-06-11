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
    enabled = _env_bool("OBSIDIAN_ENABLED", default=True)
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


def build_obsidian_sync_context() -> str:
    """English system-prompt block for COCO (model answers in user language)."""
    st = get_obsidian_sync_status()
    if not st["enabled"]:
        return (
            f"OBSIDIAN_SYNC_RUNTIME_MARKER: {OBSIDIAN_SYNC_MARKER}\n\n"
            "Obsidian optional Markdown export (separate from AFFiNE Second Brain):\n"
            "- OBSIDIAN_ENABLED=false — Obsidian Sync is not configured.\n"
            "- If asked to connect, sync, or send to Obsidian, say Obsidian Sync is not configured.\n"
            "- Never claim sync succeeded or that a note was written inside Obsidian.\n"
        )
    if st["mode"] == "uri" and not st["sync_enabled"]:
        return (
            f"OBSIDIAN_SYNC_RUNTIME_MARKER: {OBSIDIAN_SYNC_MARKER}\n\n"
            "Obsidian URI mode (optional Markdown export — AFFiNE remains the primary Second Brain):\n"
            f"- OBSIDIAN_ENABLED=true; OBSIDIAN_MODE=uri; vault={st['vault_name']}; folder={st['default_folder']}.\n"
            "- URI mode is a local device handoff (obsidian://new on user tap), not a full API sync into the vault.\n"
            "- COCO can prepare Markdown from the visible conversation and request Obsidian open via the "
            "Sync Obsidian UI chip on user tap only.\n"
            "- Do NOT deny Obsidian connectivity. Forbidden when URI mode is active: "
            "« Non, je ne peux pas synchroniser avec Obsidian », « je ne peux pas vous connecter à Obsidian », "
            "« aucune synchronisation », « aucune capacité Obsidian », « pas de connecteur Obsidian », "
            "« aucun connecteur Obsidian actif », « Obsidian indisponible », « API Obsidian n'est pas active », "
            "« no Obsidian connector », « je ne peux pas me connecter à Obsidian ».\n"
            "- When asked (FR/EN examples): « Es ce que tu peux me connecter à Obsidian ? », "
            "« Connecte moi à Obsidian », « Je veux synchroniser avec Obsidian », « sync Obsidian », "
            "« ouvrir Obsidian », « envoyer dans Obsidian » — answer YES with substance equivalent to:\n"
            "  « Oui. COCO peut préparer une note Markdown et utiliser le bouton Sync Obsidian pour déclencher "
            "Obsidian via obsidian://new. Ce n'est pas une connexion API complète : tu valides l'envoi depuis "
            "ton appareil. »\n"
            "- Never claim from chat alone: « sync réussie », « note écrite dans Obsidian », "
            "« connexion profonde active ».\n"
            "- Direct the user to tap Sync Obsidian for the actual open action.\n"
        )
    if st["sync_enabled"] and st["mode"] == "local_rest":
        return (
            f"OBSIDIAN_SYNC_RUNTIME_MARKER: {OBSIDIAN_SYNC_MARKER}\n\n"
            "Obsidian local REST mode is flagged enabled, but COCO must only claim direct vault write/sync "
            "after explicit connector confirmation. Until confirmed, describe URI/chip flow only and do not say "
            "« sync réussie » or « note écrite dans Obsidian ».\n"
        )
    return (
        f"OBSIDIAN_SYNC_RUNTIME_MARKER: {OBSIDIAN_SYNC_MARKER}\n\n"
        f"Obsidian export enabled (mode={st['mode']}); use Sync Obsidian chip for user-triggered actions. "
        "Do not claim deep sync or vault write without connector confirmation.\n"
    )
