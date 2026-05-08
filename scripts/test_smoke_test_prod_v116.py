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
    build_summary,
    classify_result,
    sanitize_output,
)


def main() -> int:
    s = sanitize_output("Authorization: Bearer abcdefghijklmnop")
    assert "[REDACTED]" in s

    r1 = classify_result(endpoint="/health", method="GET", status_code=200, elapsed_ms=12.0, payload={"ok": True})
    assert r1["status"] == STATUS_GREEN

    r2 = classify_result(
        endpoint="/decision/arbitration/last",
        method="GET",
        status_code=200,
        elapsed_ms=15.0,
        payload={"status": "empty"},
    )
    assert r2["status"] == STATUS_WARNING

    r3 = classify_result(endpoint="/health", method="GET", status_code=500, elapsed_ms=20.0, payload={})
    assert r3["status"] == STATUS_FAILED

    summary = build_summary(
        [
            {"method": "GET", "endpoint": "/a", "status": STATUS_GREEN, "elapsed_ms": 10.0},
            {"method": "GET", "endpoint": "/b", "status": STATUS_WARNING, "elapsed_ms": 20.0},
            {"method": "GET", "endpoint": "/c", "status": STATUS_FAILED, "elapsed_ms": 30.0},
        ]
    )
    assert summary["total"] == 3
    assert summary["green"] == 1
    assert summary["warnings"] == 1
    assert summary["failed"] == 1
    assert summary["prod_green"] is False
    assert summary["slowest_endpoint"]["endpoint"] == "/c"
    print("OK smoke_test_prod_v116_helpers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

