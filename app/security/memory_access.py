"""Scoped memory HTTP access helpers (P0)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.config import IS_PROD


def memory_account_key(user: dict) -> str:
    uid = user.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="Utilisateur invalide")
    return f"user-{uid}"


def filter_memory_entries(entries: list[dict] | None, user_key: str) -> list[dict]:
    uk = (user_key or "").strip()
    if not uk:
        return []
    out: list[dict] = []
    for entry in entries or []:
        if str(entry.get("user_id") or "") == uk:
            out.append(entry)
    return out


def memory_entry_owned(entry: dict | None, user_key: str) -> bool:
    if not entry:
        return False
    return str(entry.get("user_id") or "") == (user_key or "").strip()


def deny_unscoped_memory_in_prod() -> None:
    if IS_PROD:
        raise HTTPException(status_code=403, detail="Endpoint mémoire global désactivé en production")


def deny_memory_mutation_in_prod() -> None:
    if IS_PROD:
        raise HTTPException(status_code=403, detail="Mutation mémoire globale désactivée en production")


def memory_items_response(items: list[dict], user_key: str) -> dict[str, Any]:
    scoped = filter_memory_entries(items, user_key)
    return {"status": "ok", "count": len(scoped), "items": scoped}


def memory_entries_payload(entries: list[dict], user_key: str, **extra: Any) -> dict[str, Any]:
    scoped = filter_memory_entries(entries, user_key)
    payload: dict[str, Any] = {"status": "ok", "count": len(scoped), "entries": scoped}
    payload.update(extra)
    return payload


def require_memory_trace_owner(out: dict[str, Any], user_key: str) -> dict[str, Any]:
    if out.get("status") == "not_found":
        return out
    creation = out.get("creation") or {}
    if str(creation.get("user_id") or "") != user_key:
        raise HTTPException(status_code=403, detail="Accès mémoire refusé")
    return out


def lookup_owned_entry(memory_id: str, user_key: str) -> dict:
    from app.memory.fractal_memory import entries_snapshot_for_tests

    mid = (memory_id or "").strip()
    for entry in entries_snapshot_for_tests():
        if str(entry.get("id") or "") != mid:
            continue
        if memory_entry_owned(entry, user_key):
            return entry
        raise HTTPException(status_code=403, detail="Accès mémoire refusé")
    raise HTTPException(status_code=404, detail="Mémoire introuvable")


def filter_payload_memory_lists(payload: dict[str, Any], user_key: str) -> dict[str, Any]:
    out = dict(payload)
    for key in ("items", "entries", "events", "selected", "rejected"):
        value = out.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict) and "user_id" in value[0]:
            out[key] = filter_memory_entries(value, user_key)
            if key in ("items", "entries", "events"):
                out["count"] = len(out[key])
    return out
