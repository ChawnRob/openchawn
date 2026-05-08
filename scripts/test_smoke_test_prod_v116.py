#!/usr/bin/env python3
"""Unit tests for smoke_test_prod_v116 helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.smoke_test_prod_v116 import (  # noqa: E402
    STATUS_FAILED,
    STATUS_GREEN,
    STATUS_WARNING,
    TIER_CRITICAL,
    TIER_IMPORTANT,
    TIER_OPTIONAL,
    TIER_SETUP,
    build_summary,
    classify_result,
    sanitize_output,
)


def main() -> int:
    s = sanitize_output("Authorization: Bearer abcdefghijklmnop")
    assert "[REDACTED]" in s

    r1 = classify_result(endpoint="/health", method="GET", status_code=200, elapsed_ms=12.0, payload={"ok": True}, tier=TIER_CRITICAL)
    assert r1["status"] == STATUS_GREEN

    rw = classify_result(
        endpoint="/decision/arbitration/last",
        method="GET",
        status_code=200,
        elapsed_ms=15.0,
        payload={"status": "empty"},
        tier=TIER_OPTIONAL,
    )
    assert rw["status"] == STATUS_WARNING

    r3 = classify_result(endpoint="/health", method="GET", status_code=500, elapsed_ms=20.0, payload={}, tier=TIER_CRITICAL)
    assert r3["status"] == STATUS_FAILED

    rg = classify_result(
        endpoint="/guest/session",
        method="POST",
        status_code=200,
        elapsed_ms=5.0,
        payload={"session_id": "guest_abc", "quota_remaining": 5},
        tier=TIER_SETUP,
    )
    assert rg["status"] == STATUS_GREEN

    rdry = classify_result(
        endpoint="/health/language/chat-dry-run",
        method="POST",
        status_code=200,
        elapsed_ms=8.0,
        payload={
            "route_used": "POST /chat",
            "profile_used": "fluxorca",
            "detected_language": "en",
            "forced_french_runtime_detected": False,
        },
        tier=TIER_OPTIONAL,
    )
    assert rdry["status"] == STATUS_GREEN

    r_bad_chat = classify_result(
        endpoint="/chat",
        method="POST",
        status_code=200,
        elapsed_ms=900.0,
        payload={"output": "Désolé, je ne peux m'exprimer qu'en français.", "lang": "en"},
        tier=TIER_CRITICAL,
    )
    assert r_bad_chat["status"] == STATUS_FAILED

    rchat = classify_result(
        endpoint="/chat",
        method="POST",
        status_code=200,
        elapsed_ms=900.0,
        payload={"output": "OpenChawn is an AI orchestration layer.", "lang": "en"},
        tier=TIER_CRITICAL,
    )
    assert rchat["status"] == STATUS_GREEN

    summary_critical_fail = build_summary(
        [
            {"method": "POST", "endpoint": "/guest/session", "tier": TIER_SETUP, "status": STATUS_GREEN, "elapsed_ms": 1.0},
            {"method": "GET", "endpoint": "/health", "tier": TIER_CRITICAL, "status": STATUS_GREEN, "elapsed_ms": 2.0},
            {"method": "POST", "endpoint": "/chat", "tier": TIER_CRITICAL, "status": STATUS_FAILED, "elapsed_ms": 3.0},
        ]
    )
    assert summary_critical_fail["prod_green"] is False

    summary_optional_warning = build_summary(
        [
            {"method": "POST", "endpoint": "/guest/session", "tier": TIER_SETUP, "status": STATUS_GREEN, "elapsed_ms": 1.0},
            {"method": "GET", "endpoint": "/health", "tier": TIER_CRITICAL, "status": STATUS_GREEN, "elapsed_ms": 2.0},
            {"method": "POST", "endpoint": "/chat", "tier": TIER_CRITICAL, "status": STATUS_GREEN, "elapsed_ms": 3.0},
            {"method": "POST", "endpoint": "/api/chat", "tier": TIER_CRITICAL, "status": STATUS_GREEN, "elapsed_ms": 4.0},
            {"method": "GET", "endpoint": "/memory/graph/hubs", "tier": TIER_OPTIONAL, "status": STATUS_WARNING, "elapsed_ms": 5.0},
            {"method": "GET", "endpoint": "/health/providers", "tier": TIER_IMPORTANT, "status": STATUS_WARNING, "elapsed_ms": 6.0},
        ]
    )
    assert summary_optional_warning["prod_green"] is True

    summary_mix = build_summary(
        [
            {"method": "GET", "endpoint": "/health", "tier": TIER_CRITICAL, "status": STATUS_GREEN, "elapsed_ms": 10.0},
            {"method": "GET", "endpoint": "/b", "tier": TIER_IMPORTANT, "status": STATUS_WARNING, "elapsed_ms": 20.0},
            {"method": "GET", "endpoint": "/c", "tier": TIER_OPTIONAL, "status": STATUS_FAILED, "elapsed_ms": 30.0},
        ]
    )
    assert summary_mix["total"] == 3
    assert summary_mix["green"] == 1
    assert summary_mix["warnings"] == 1
    assert summary_mix["failed"] == 1
    assert summary_mix["prod_green"] is True

    summary_all_fail = build_summary(
        [
            {"method": "POST", "endpoint": "/guest/session", "tier": TIER_SETUP, "status": STATUS_FAILED, "elapsed_ms": 1.0},
            {"method": "GET", "endpoint": "/health", "tier": TIER_CRITICAL, "status": STATUS_GREEN, "elapsed_ms": 2.0},
        ]
    )
    assert summary_all_fail["prod_green"] is False

    print("OK smoke_test_prod_v116_helpers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
