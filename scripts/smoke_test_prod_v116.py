#!/usr/bin/env python3
"""Production smoke test pack for OpenChawn V11.6."""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from typing import Any

import requests

DEFAULT_BASE_URL = "https://www.openchawn.com"
DEFAULT_TIMEOUT_S = 10.0

STATUS_GREEN = "GREEN"
STATUS_WARNING = "WARNING"
STATUS_FAILED = "FAILED"


def sanitize_output(value: str) -> str:
    s = str(value or "")
    s = re.sub(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._-]+", r"\1[REDACTED]", s)
    s = re.sub(r"(?i)\b(api[_-]?key|token|secret)\b\s*[:=]\s*\S+", r"\1=[REDACTED]", s)
    s = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", s)
    return s[:500]


def classify_result(
    *,
    endpoint: str,
    method: str,
    status_code: int | None,
    elapsed_ms: float,
    payload: Any,
    error: str = "",
) -> dict[str, Any]:
    if error:
        return {"status": STATUS_FAILED, "reason": sanitize_output(error), "code": status_code, "elapsed_ms": round(elapsed_ms, 2)}
    if status_code is None or status_code < 200 or status_code >= 300:
        return {
            "status": STATUS_FAILED,
            "reason": f"http_status_{status_code}",
            "code": status_code,
            "elapsed_ms": round(elapsed_ms, 2),
        }

    if method == "GET" and endpoint in ("/decision/arbitration/last", "/decision/arbitration/report"):
        if isinstance(payload, dict) and str(payload.get("status") or "") in ("empty", "no_viable_option"):
            return {
                "status": STATUS_WARNING,
                "reason": "empty_last_arbitration",
                "code": status_code,
                "elapsed_ms": round(elapsed_ms, 2),
            }

    if method == "GET" and endpoint in (
        "/memory/importance/top",
        "/memory/graph/hubs",
        "/memory/temporal/rising",
    ):
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list) and len(items) == 0:
                return {
                    "status": STATUS_WARNING,
                    "reason": "empty_items",
                    "code": status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                }

    return {"status": STATUS_GREEN, "reason": "ok", "code": status_code, "elapsed_ms": round(elapsed_ms, 2)}


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    green = sum(1 for r in results if r.get("status") == STATUS_GREEN)
    warnings = sum(1 for r in results if r.get("status") == STATUS_WARNING)
    failed = sum(1 for r in results if r.get("status") == STATUS_FAILED)
    latencies = [float(r.get("elapsed_ms") or 0.0) for r in results]
    slowest = max(results, key=lambda r: float(r.get("elapsed_ms") or 0.0)) if results else None
    return {
        "total": total,
        "green": green,
        "warnings": warnings,
        "failed": failed,
        "prod_green": failed == 0,
        "slowest_endpoint": {
            "method": slowest.get("method"),
            "endpoint": slowest.get("endpoint"),
            "elapsed_ms": round(float(slowest.get("elapsed_ms") or 0.0), 2),
        }
        if slowest
        else None,
        "average_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
    }


def _check(
    session: requests.Session,
    *,
    base_url: str,
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    t0 = time.perf_counter()
    status_code = None
    parsed: Any = None
    error = ""
    try:
        if method == "GET":
            resp = session.get(url, timeout=timeout_s)
        else:
            resp = session.post(url, json=payload or {}, timeout=timeout_s)
        status_code = resp.status_code
        try:
            parsed = resp.json()
        except Exception:
            if method == "GET" or endpoint in ("/decision/arbitration/simulate", "/api/chat"):
                error = "invalid_json_response"
    except requests.Timeout:
        error = "timeout"
    except Exception as exc:
        error = f"exception:{exc.__class__.__name__}"

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    c = classify_result(
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        payload=parsed,
        error=error,
    )
    return {
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "elapsed_ms": c["elapsed_ms"],
        "status": c["status"],
        "reason": c["reason"],
    }


def _print_result(r: dict[str, Any]) -> None:
    print(f"[{r['status']}] {r['method']} {r['endpoint']} {r.get('status_code')} {int(float(r.get('elapsed_ms') or 0.0))}ms {sanitize_output(r.get('reason') or '')}")


def run_smoke(*, base_url: str, fail_fast: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks = [
        ("GET", "/health", None),
        ("GET", "/health/providers", None),
        ("GET", "/health/language", None),
        ("GET", "/memory/semantic/health", None),
        ("GET", "/memory/semantic/stats", None),
        ("GET", "/memory/importance/health", None),
        ("GET", "/memory/importance/top", None),
        ("GET", "/memory/graph/stats", None),
        ("GET", "/memory/graph/hubs", None),
        ("GET", "/memory/temporal/snapshot", None),
        ("GET", "/memory/temporal/rising", None),
        ("GET", "/memory/contradictions/report", None),
        ("GET", "/decision/arbitration/report", None),
        ("GET", "/decision/arbitration/last", None),
        (
            "POST",
            "/decision/arbitration/simulate",
            {
                "project": "openchawn",
                "decision_type": "provider_strategy",
                "options": [
                    {"title": "Use DeepSeek as default provider", "source_memory_ids": []},
                    {"title": "Use OpenAI as elite fallback", "source_memory_ids": []},
                ],
            },
        ),
        (
            "POST",
            "/api/chat",
            {
                "message": "Explain OpenChawn in English in one short sentence.",
                "project": "openchawn",
            },
        ),
    ]
    out: list[dict[str, Any]] = []
    with requests.Session() as s:
        for method, endpoint, payload in checks:
            r = _check(s, base_url=base_url, method=method, endpoint=endpoint, payload=payload)
            out.append(r)
            _print_result(r)
            if fail_fast and r.get("status") == STATUS_FAILED:
                break
    summary = build_summary(out)
    print(
        f"[SUMMARY] total={summary['total']} green={summary['green']} warnings={summary['warnings']} "
        f"failed={summary['failed']} prod_green={summary['prod_green']} avg_ms={summary['average_latency_ms']}"
    )
    return out, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenChawn production smoke test V11.6")
    parser.add_argument("--base-url", default="", help="Base URL for production checks")
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failed endpoint")
    args = parser.parse_args()

    base_url = (args.base_url or os.getenv("OPENCHAWN_PROD_URL") or DEFAULT_BASE_URL).strip()
    results, summary = run_smoke(base_url=base_url, fail_fast=bool(args.fail_fast))
    if args.json:
        print(json.dumps({"base_url": base_url, "summary": summary, "results": results}, ensure_ascii=False, indent=2))
    return 1 if int(summary.get("failed") or 0) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

