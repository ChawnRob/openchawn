"""
Guest quota observability — in-process counters and recent events for staging diagnostics.

No secrets: session ids and IPs are reduced to short prefixes / fingerprints only.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any

_LOCK = Lock()
_STARTED_AT = time.time()

_COUNTERS: dict[str, int] = defaultdict(int)
_RECENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=100)

OBSERVABILITY_VERSION = "guest_quota_obs_v1"


def _ip_fingerprint(ip: str) -> str:
    raw = (ip or "unknown").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _session_prefix(session_id: str) -> str:
    sid = (session_id or "").strip()
    return sid[:12] if sid else ""


def record_guest_quota_event(
    *,
    event: str,
    session_id: str = "",
    ip: str = "",
    remaining: int | None = None,
    limit: int | None = None,
    block_reason: str | None = None,
) -> None:
    """Record a quota-related event (thread-safe, in-memory)."""
    payload: dict[str, Any] = {
        "ts": time.time(),
        "event": event,
        "session_prefix": _session_prefix(session_id),
        "ip_fingerprint": _ip_fingerprint(ip),
    }
    if remaining is not None:
        payload["remaining"] = int(remaining)
    if limit is not None:
        payload["limit"] = int(limit)
    if block_reason:
        payload["block_reason"] = block_reason

    with _LOCK:
        _COUNTERS[event] += 1
        if block_reason:
            _COUNTERS[f"block_reason:{block_reason}"] += 1
        _RECENT_EVENTS.append(payload)


def record_chat_rate_limit_blocked(*, ip: str, path: str, kind: str) -> None:
    """Distinguish middleware 429 from guest daily quota 429 in dashboards."""
    payload: dict[str, Any] = {
        "ts": time.time(),
        "event": "chat_rate_limit_blocked",
        "ip_fingerprint": _ip_fingerprint(ip),
        "block_reason": kind,
        "path": path,
    }
    with _LOCK:
        _COUNTERS["chat_rate_limit_blocked"] += 1
        _COUNTERS[f"rate_limit:{kind}"] += 1
        _RECENT_EVENTS.append(payload)


def reset_guest_quota_observability_for_tests() -> None:
    """Test-only reset."""
    with _LOCK:
        _COUNTERS.clear()
        _RECENT_EVENTS.clear()


def _counter_snapshot() -> dict[str, int]:
    with _LOCK:
        return dict(_COUNTERS)


def _recent_snapshot(limit: int = 25) -> list[dict[str, Any]]:
    cap = max(1, min(limit, 100))
    with _LOCK:
        items = list(_RECENT_EVENTS)[-cap:]
    return [{k: v for k, v in ev.items()} for ev in items]


def build_live_store_snapshot() -> dict[str, Any]:
    """Aggregate in-memory guest session store (no raw IPs or full session ids)."""
    from app.auth import guest as guest_mod
    from app.settings import get_settings

    cap = get_settings().guest_daily_limit
    today = guest_mod._today()  # noqa: SLF001 — observability coupling

    active_sessions = 0
    at_daily_limit = 0
    message_counts: list[int] = []
    ip_fingerprints: set[str] = set()

    for session in guest_mod._sessions.values():  # noqa: SLF001
        session.reset_if_new_day()
        if session.date_key != today:
            continue
        active_sessions += 1
        message_counts.append(int(session.message_count))
        if session.message_count >= cap:
            at_daily_limit += 1
        ip_fingerprints.add(_ip_fingerprint(session.ip))

    avg_used = round(sum(message_counts) / len(message_counts), 2) if message_counts else 0.0

    return {
        "active_sessions_today": active_sessions,
        "sessions_at_daily_limit": at_daily_limit,
        "distinct_ip_fingerprints_today": len(ip_fingerprints),
        "avg_messages_consumed_today": avg_used,
        "configured_daily_limit": cap,
        "reset_window": "utc_calendar_day",
        "max_sessions_per_ip": guest_mod._MAX_SESSIONS_PER_IP,
    }


def get_guest_quota_observability_overview(*, recent_limit: int = 25) -> dict[str, Any]:
    """Safe JSON overview for staging ops (no secrets)."""
    counters = _counter_snapshot()
    blocks = sum(v for k, v in counters.items() if k.startswith("block_reason:"))
    allows = int(counters.get("quota_message_ok", 0))

    return {
        "status": "ok",
        "observability_version": OBSERVABILITY_VERSION,
        "uptime_seconds": int(time.time() - _STARTED_AT),
        "counters": counters,
        "summary": {
            "quota_checks_allowed": allows,
            "quota_checks_blocked": blocks,
            "chat_rate_limit_blocks": int(counters.get("chat_rate_limit_blocked", 0)),
            "sessions_created": int(counters.get("guest_session_created", 0)),
            "sessions_reused": int(counters.get("guest_session_reused", 0)),
        },
        "live_store": build_live_store_snapshot(),
        "recent_events": _recent_snapshot(recent_limit),
        "log_correlation_fields": [
            "event",
            "session_prefix",
            "ip_fingerprint",
            "block_reason",
            "quota_remaining",
        ],
        "note": (
            "Guest daily quota 429 uses French detail in /chat; filter logs with "
            "block_reason=daily_limit_exceeded. Middleware 429 uses "
            "event=chat_rate_limit_blocked. Do not expose this endpoint on public prod without review."
        ),
    }
