"""
Guest session management — anonymous chat with daily quota.
Zero external dependencies, in-memory store with daily cleanup.
"""
import logging
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone

from app.core.guest_quota_observability import record_guest_quota_event
from app.settings import get_settings

logger = logging.getLogger("openchawn.guest")


def _guest_cap() -> int:
    """Limite jour courant ; relit les settings pour tests / ENV reload."""
    return get_settings().guest_daily_limit


# ── In-memory store ──────────────────────────────────────

class _GuestSession:
    __slots__ = ("session_id", "ip", "message_count", "date_key", "created_at")

    def __init__(self, session_id: str, ip: str):
        self.session_id = session_id
        self.ip = ip
        self.message_count = 0
        self.date_key = _today()
        self.created_at = time.time()

    def reset_if_new_day(self):
        today = _today()
        if self.date_key != today:
            self.message_count = 0
            self.date_key = today


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# session_id -> _GuestSession
_sessions: dict[str, _GuestSession] = {}

# IP -> set of session_ids (prevent IP abuse)
_ip_sessions: dict[str, set[str]] = defaultdict(set)

_MAX_SESSIONS_PER_IP = 5


# ── Public API ───────────────────────────────────────────

def create_guest_session(ip: str) -> dict:
    """Create a new anonymous guest session. Returns session info."""
    # Cleanup old sessions first
    _cleanup_stale_sessions()

    # Limit sessions per IP
    active = _ip_sessions.get(ip, set())
    if len(active) >= _MAX_SESSIONS_PER_IP:
        # Reuse the most recent one instead of creating new
        for sid in list(active):
            if sid in _sessions:
                session = _sessions[sid]
                session.reset_if_new_day()
                cap = _guest_cap()
                remaining = max(0, cap - session.message_count)
                logger.info(
                    f"guest session reused | session={sid[:12]}… | ip={ip} | "
                    f"quota_remaining={remaining}"
                )
                record_guest_quota_event(
                    event="guest_session_reused",
                    session_id=sid,
                    ip=ip,
                    remaining=remaining,
                    limit=cap,
                )
                return _session_to_dict(session)
        # All stale, clear and create new
        _ip_sessions[ip].clear()

    session_id = f"guest_{secrets.token_urlsafe(24)}"
    session = _GuestSession(session_id, ip)
    _sessions[session_id] = session
    _ip_sessions[ip].add(session_id)

    cap = _guest_cap()
    logger.info(
        f"guest session created | session={session_id[:12]}… | ip={ip} | "
        f"quota_remaining={cap}"
    )
    record_guest_quota_event(
        event="guest_session_created",
        session_id=session_id,
        ip=ip,
        remaining=cap,
        limit=cap,
    )
    return _session_to_dict(session)


def check_guest_quota(session_id: str, ip: str) -> dict:
    """
    Check and consume one message from the guest quota.
    Returns {"allowed": bool, "remaining": int, "limit": int}.
    """
    session = _sessions.get(session_id)

    if not session:
        cap = _guest_cap()
        reason = "unknown_session"
        logger.warning(
            f"guest session unknown | session={session_id[:12]}… | block_reason={reason}"
        )
        record_guest_quota_event(
            event="quota_check_blocked",
            session_id=session_id,
            ip=ip,
            remaining=0,
            limit=cap,
            block_reason=reason,
        )
        return {"allowed": False, "remaining": 0, "limit": cap, "block_reason": reason}

    # Verify IP matches (prevent session hijacking)
    if session.ip != ip:
        cap = _guest_cap()
        reason = "ip_mismatch"
        logger.warning(
            f"guest session ip mismatch | session={session_id[:12]}… | "
            f"expected={session.ip} got={ip} | block_reason={reason}"
        )
        record_guest_quota_event(
            event="quota_check_blocked",
            session_id=session_id,
            ip=ip,
            remaining=0,
            limit=cap,
            block_reason=reason,
        )
        return {"allowed": False, "remaining": 0, "limit": cap, "block_reason": reason}

    session.reset_if_new_day()

    cap = _guest_cap()
    remaining = cap - session.message_count

    if remaining <= 0:
        reason = "daily_limit_exceeded"
        logger.info(
            f"blocked by quota | session={session_id[:12]}… | ip={ip} | "
            f"count={session.message_count}/{cap} | block_reason={reason}"
        )
        record_guest_quota_event(
            event="quota_check_blocked",
            session_id=session_id,
            ip=ip,
            remaining=0,
            limit=cap,
            block_reason=reason,
        )
        return {
            "allowed": False,
            "remaining": 0,
            "limit": cap,
            "block_reason": reason,
        }

    # Consume one message
    session.message_count += 1
    remaining -= 1

    logger.info(
        f"guest message ok | session={session_id[:12]}… | ip={ip} | "
        f"quota_remaining={remaining}/{cap}"
    )
    record_guest_quota_event(
        event="quota_message_ok",
        session_id=session_id,
        ip=ip,
        remaining=remaining,
        limit=cap,
    )
    return {"allowed": True, "remaining": remaining, "limit": cap}


def get_guest_quota_status(session_id: str) -> dict | None:
    """Return current quota status without consuming a message."""
    session = _sessions.get(session_id)
    if not session:
        return None
    session.reset_if_new_day()
    cap = _guest_cap()
    remaining = max(0, cap - session.message_count)
    return {"remaining": remaining, "limit": cap, "used": session.message_count}


# ── Internal helpers ─────────────────────────────────────

def _session_to_dict(session: _GuestSession) -> dict:
    cap = _guest_cap()
    remaining = max(0, cap - session.message_count)
    return {
        "session_id": session.session_id,
        "quota": {"remaining": remaining, "limit": cap},
    }


def _cleanup_stale_sessions():
    """Remove sessions older than 24h."""
    cutoff = time.time() - 86400
    stale = [sid for sid, s in _sessions.items() if s.created_at < cutoff]
    for sid in stale:
        session = _sessions.pop(sid, None)
        if session:
            ip_set = _ip_sessions.get(session.ip)
            if ip_set:
                ip_set.discard(sid)
                if not ip_set:
                    del _ip_sessions[session.ip]
    if stale:
        logger.debug(f"guest cleanup: {len(stale)} stale sessions removed")
