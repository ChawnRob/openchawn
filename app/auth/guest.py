"""
Guest session management — anonymous chat with daily quota.
Zero external dependencies, in-memory store with daily cleanup.
"""
import logging
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone

from app.config import GUEST_DAILY_LIMIT

logger = logging.getLogger("openchawn.guest")


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
                logger.info(
                    f"guest session reused | session={sid[:12]}… | ip={ip} | "
                    f"quota_remaining={max(0, GUEST_DAILY_LIMIT - session.message_count)}"
                )
                return _session_to_dict(session)
        # All stale, clear and create new
        _ip_sessions[ip].clear()

    session_id = f"guest_{secrets.token_urlsafe(24)}"
    session = _GuestSession(session_id, ip)
    _sessions[session_id] = session
    _ip_sessions[ip].add(session_id)

    logger.info(
        f"guest session created | session={session_id[:12]}… | ip={ip} | "
        f"quota_remaining={GUEST_DAILY_LIMIT}"
    )
    return _session_to_dict(session)


def check_guest_quota(session_id: str, ip: str) -> dict:
    """
    Check and consume one message from the guest quota.
    Returns {"allowed": bool, "remaining": int, "limit": int}.
    """
    session = _sessions.get(session_id)

    if not session:
        logger.warning(f"guest session unknown | session={session_id[:12]}…")
        return {"allowed": False, "remaining": 0, "limit": GUEST_DAILY_LIMIT}

    # Verify IP matches (prevent session hijacking)
    if session.ip != ip:
        logger.warning(
            f"guest session ip mismatch | session={session_id[:12]}… | "
            f"expected={session.ip} got={ip}"
        )
        return {"allowed": False, "remaining": 0, "limit": GUEST_DAILY_LIMIT}

    session.reset_if_new_day()

    remaining = GUEST_DAILY_LIMIT - session.message_count

    if remaining <= 0:
        logger.info(
            f"blocked by quota | session={session_id[:12]}… | ip={ip} | "
            f"count={session.message_count}/{GUEST_DAILY_LIMIT}"
        )
        return {"allowed": False, "remaining": 0, "limit": GUEST_DAILY_LIMIT}

    # Consume one message
    session.message_count += 1
    remaining -= 1

    logger.info(
        f"guest message ok | session={session_id[:12]}… | ip={ip} | "
        f"quota_remaining={remaining}/{GUEST_DAILY_LIMIT}"
    )
    return {"allowed": True, "remaining": remaining, "limit": GUEST_DAILY_LIMIT}


def get_guest_quota_status(session_id: str) -> dict | None:
    """Return current quota status without consuming a message."""
    session = _sessions.get(session_id)
    if not session:
        return None
    session.reset_if_new_day()
    remaining = max(0, GUEST_DAILY_LIMIT - session.message_count)
    return {"remaining": remaining, "limit": GUEST_DAILY_LIMIT, "used": session.message_count}


# ── Internal helpers ─────────────────────────────────────

def _session_to_dict(session: _GuestSession) -> dict:
    remaining = max(0, GUEST_DAILY_LIMIT - session.message_count)
    return {
        "session_id": session.session_id,
        "quota": {"remaining": remaining, "limit": GUEST_DAILY_LIMIT},
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
