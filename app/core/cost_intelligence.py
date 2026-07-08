"""
Cost intelligence layer (P1.5-COST) — per-request cost tracking without user content.

Never stores prompts, responses, emails, or raw conversation identifiers.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from app.core.cost_pricing import (
    PricingStatus,
    compute_llm_cost_usd,
    compute_web_search_cost_usd,
    merge_pricing_status,
    usd_to_eur,
)
from app.core.cost_store import (
    clear_cost_events_store,
    persist_cost_event,
    query_cost_status,
    query_cost_summary,
)

logger = logging.getLogger("openchawn.cost.intelligence")

UserScope = Literal["guest", "user", "owner"]

_DOCUMENT_EXT_RE = re.compile(
    r"\.(pdf|docx?|xlsx?|pptx?|csv|txt|md)\b",
    re.IGNORECASE,
)

_last_debug_snapshot: dict[str, Any] = {
    "last_request_cost": 0.0,
    "last_provider": None,
    "last_model": None,
    "last_duration_ms": 0,
    "pricing_status": "unknown",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_cost_intelligence_enabled() -> bool:
    raw = (os.getenv("COST_INTELLIGENCE_ENABLED") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _sample_rate() -> float:
    raw = (os.getenv("COST_SAMPLE_RATE") or "1.0").strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 1.0


def default_currency() -> str:
    return (os.getenv("COST_DEFAULT_CURRENCY") or "EUR").strip().upper() or "EUR"


def _alert_daily_eur() -> float:
    try:
        return float(os.getenv("COST_ALERT_DAILY_EUR") or "5.0")
    except ValueError:
        return 5.0


def _alert_per_request_eur() -> float:
    try:
        return float(os.getenv("COST_ALERT_PER_REQUEST_EUR") or "0.05")
    except ValueError:
        return 0.05


def should_sample_request() -> bool:
    rate = _sample_rate()
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def anonymize_user_scope(user: dict[str, Any]) -> UserScope:
    if user.get("is_guest"):
        return "guest"
    if user.get("is_owner") or user.get("user_role") == "owner":
        return "owner"
    return "user"


def optional_scope_hash(user: dict[str, Any]) -> str:
    """Short non-reversible hash when finer granularity is needed (not stored by default)."""
    key = str(user.get("guest_session_id") or user.get("user_id") or user.get("id") or "anon")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


@dataclass
class CostEvent:
    request_id: str
    user_scope: str
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    llm_cost_usd: float
    web_search_count: int
    web_search_cost_usd: float
    vision_used: bool
    document_used: bool
    duration_ms: int
    total_cost_usd: float
    created_at: datetime
    pricing_status: PricingStatus = "complete"
    payload_bytes: int = 0

    def to_store_dict(self) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "request_id": self.request_id,
            "user_scope": self.user_scope,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "llm_cost_usd": self.llm_cost_usd,
            "web_search_count": self.web_search_count,
            "web_search_cost_usd": self.web_search_cost_usd,
            "vision_used": self.vision_used,
            "document_used": self.document_used,
            "duration_ms": self.duration_ms,
            "total_cost_usd": self.total_cost_usd,
            "created_at": self.created_at.isoformat(),
        }

    def to_debug_dict(self) -> dict[str, Any]:
        currency = default_currency()
        cost_display = self.total_cost_usd
        if currency == "EUR":
            cost_display = usd_to_eur(self.total_cost_usd)
        return {
            "cost_estimate": round(cost_display, 8),
            "cost_currency": currency,
            "cost_pricing_status": self.pricing_status,
        }


@dataclass
class ChatCostTracker:
    """Per-request cost tracker — safe to no-op when disabled."""

    request_id: str
    user_scope: str
    started_at: float = field(default_factory=time.perf_counter)
    payload_bytes: int = 0
    vision_used: bool = False
    document_used: bool = False
    web_search_count: int = 0
    web_search_provider: str = "perplexity"
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    llm_cost_usd: float = 0.0
    web_search_cost_usd: float = 0.0
    pricing_status: PricingStatus = "complete"
    enabled: bool = True
    sampled: bool = True
    _recorded: bool = field(default=False, repr=False)

    @classmethod
    def start(
        cls,
        user: dict[str, Any],
        *,
        message: str = "",
        media_id: str = "",
        image_active: bool = False,
    ) -> ChatCostTracker | None:
        if not is_cost_intelligence_enabled():
            return None
        sampled = should_sample_request()
        tracker = cls(
            request_id=uuid.uuid4().hex[:16],
            user_scope=anonymize_user_scope(user),
            payload_bytes=len(message or ""),
            vision_used=bool(image_active or (media_id or "").strip()),
            document_used=bool(_DOCUMENT_EXT_RE.search(message or "")),
            enabled=True,
            sampled=sampled,
        )
        return tracker

    def add_payload_size(self, extra_bytes: int) -> None:
        self.payload_bytes += max(0, int(extra_bytes))

    def record_web_search(self, *, count: int, provider: str) -> None:
        self.web_search_count = max(0, int(count))
        self.web_search_provider = (provider or "perplexity").strip().lower()
        cost, status = compute_web_search_cost_usd(provider=self.web_search_provider, count=self.web_search_count)
        self.web_search_cost_usd = cost
        self.pricing_status = merge_pricing_status(self.pricing_status, status)

    def record_llm(
        self,
        *,
        provider: str | None,
        model: str | None,
        input_text: str = "",
        output_text: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self.provider = (provider or None)
        self.model = (model or None) or None
        cost, inp, out, status = compute_llm_cost_usd(
            provider=self.provider,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_text=input_text,
            output_text=output_text,
        )
        self.llm_cost_usd = cost
        self.input_tokens = inp
        self.output_tokens = out
        self.pricing_status = merge_pricing_status(self.pricing_status, status)
        self.add_payload_size(len(input_text) + len(output_text))

    def finish(self) -> CostEvent | None:
        if not self.enabled or not self.sampled or self._recorded:
            return None
        self._recorded = True
        duration_ms = int((time.perf_counter() - self.started_at) * 1000)
        total = round(self.llm_cost_usd + self.web_search_cost_usd, 8)
        event = CostEvent(
            request_id=self.request_id,
            user_scope=self.user_scope,
            provider=self.provider,
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            llm_cost_usd=self.llm_cost_usd,
            web_search_count=self.web_search_count,
            web_search_cost_usd=self.web_search_cost_usd,
            vision_used=self.vision_used,
            document_used=self.document_used,
            duration_ms=duration_ms,
            total_cost_usd=total,
            created_at=_now_utc(),
            pricing_status=self.pricing_status,
            payload_bytes=self.payload_bytes,
        )
        try:
            backend = persist_cost_event(event.to_store_dict())
            _update_last_debug(event)
            _check_cost_alerts(event)
            logger.info(
                "cost_event recorded | backend=%s | scope=%s | provider=%s | total_usd=%.6f | duration_ms=%s",
                backend,
                event.user_scope,
                event.provider or "none",
                event.total_cost_usd,
                event.duration_ms,
            )
        except Exception as exc:
            logger.warning(
                "cost_event persist failed (non-blocking) | error=%s",
                exc.__class__.__name__,
            )
        return event


def record_chat_cost_safe(tracker: ChatCostTracker | None) -> CostEvent | None:
    """Persist cost event; never raises."""
    if tracker is None:
        return None
    try:
        return tracker.finish()
    except Exception as exc:
        logger.warning(
            "cost tracking failed (non-blocking) | error=%s",
            exc.__class__.__name__,
        )
        return None


def _update_last_debug(event: CostEvent) -> None:
    global _last_debug_snapshot
    _last_debug_snapshot = {
        "last_request_cost": event.total_cost_usd,
        "last_provider": event.provider,
        "last_model": event.model,
        "last_duration_ms": event.duration_ms,
        "pricing_status": event.pricing_status,
    }


def _check_cost_alerts(event: CostEvent) -> None:
    total_eur = usd_to_eur(event.total_cost_usd)
    if total_eur >= _alert_per_request_eur():
        logger.warning(
            "cost_alert per_request | scope=%s | total_eur=%.4f | threshold=%.4f",
            event.user_scope,
            total_eur,
            _alert_per_request_eur(),
        )
    status = query_cost_status()
    daily_eur = usd_to_eur(float(status.get("daily_cost_estimate") or 0))
    if daily_eur >= _alert_daily_eur():
        logger.warning(
            "cost_alert daily | total_eur=%.4f | threshold=%.4f | requests=%s",
            daily_eur,
            _alert_daily_eur(),
            status.get("daily_request_count"),
        )


def get_cost_runtime_status() -> dict[str, Any]:
    store_status = query_cost_status()
    return {
        "enabled": is_cost_intelligence_enabled(),
        "storage_backend": store_status.get("storage_backend", "unknown"),
        "currency": default_currency(),
        "pricing_status": _last_debug_snapshot.get("pricing_status", "unknown"),
        "events_count": store_status.get("events_count", 0),
        "last_event_at": store_status.get("last_event_at"),
        "daily_cost_estimate": store_status.get("daily_cost_estimate", 0.0),
        "daily_request_count": store_status.get("daily_request_count", 0),
        "sample_rate": _sample_rate(),
    }


def get_cost_summary(*, period: str = "today") -> dict[str, Any]:
    period_norm = period if period in ("today", "7d", "30d") else "today"
    return query_cost_summary(period=period_norm)


def get_cost_debug_snapshot() -> dict[str, Any]:
    return dict(_last_debug_snapshot)


def reset_cost_intelligence_for_tests() -> None:
    global _last_debug_snapshot
    clear_cost_events_store()
    _last_debug_snapshot = {
        "last_request_cost": 0.0,
        "last_provider": None,
        "last_model": None,
        "last_duration_ms": 0,
        "pricing_status": "unknown",
    }
