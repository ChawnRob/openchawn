#!/usr/bin/env python3
"""Production smoke test pack for OpenChawn V11.6 (tiered: CRITICAL / IMPORTANT / OPTIONAL)."""

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

TIER_SETUP = "SETUP"
TIER_CRITICAL = "CRITICAL"
TIER_IMPORTANT = "IMPORTANT"
TIER_OPTIONAL = "OPTIONAL"


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
    tier: str = "",
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

    if method == "POST" and endpoint == "/guest/session":
        if not isinstance(payload, dict) or not str(payload.get("session_id") or "").strip():
            return {
                "status": STATUS_FAILED,
                "reason": "missing_session_id",
                "code": status_code,
                "elapsed_ms": round(elapsed_ms, 2),
            }

    def _violates(txt: str) -> bool:
        try:
            from app.core.runtime_language_guard import (  # type: ignore
                RESPONSE_FORCED_FRENCH_SUBSTRINGS,
                _normalize_for_match,
            )

            norm = _normalize_for_match(txt)
            return any(pat in norm for pat in RESPONSE_FORCED_FRENCH_SUBSTRINGS)
        except Exception:
            lt = txt.lower().replace("\u2019", "'").replace("`", "").replace("\u201c", "").replace("\u201d", "")
            return (
                "ne peux m'exprimer qu'en francais" in lt
                or "ne peux m'exprimer qu'en français" in lt
                or "uniquement en francais" in lt
                or "uniquement en français" in lt
                or "repondre uniquement en francais" in lt
                or "regles strictes" in lt
            )

    if method == "POST" and endpoint in ("/chat", "/api/chat"):
        if not isinstance(payload, dict):
            return {
                "status": STATUS_FAILED,
                "reason": "invalid_chat_payload",
                "code": status_code,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        out_txt = str(payload.get("output") or "").strip()
        if out_txt and _violates(out_txt):
            return {
                "status": STATUS_FAILED,
                "reason": "disallowed_french_only_excuse_in_output",
                "code": status_code,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        if out_txt:
            return {"status": STATUS_GREEN, "reason": "ok", "code": status_code, "elapsed_ms": round(elapsed_ms, 2)}
        detail = payload.get("detail")
        hint = ""
        if isinstance(detail, list) and detail:
            hint = sanitize_output(str(detail[0].get("msg") if isinstance(detail[0], dict) else detail[0]))
        elif isinstance(detail, dict):
            hint = sanitize_output(str(detail))
        elif detail is not None:
            hint = sanitize_output(str(detail))
        reason = hint or "empty_chat_output"
        return {
            "status": STATUS_FAILED,
            "reason": reason,
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

    if method == "GET" and tier == TIER_OPTIONAL and endpoint in (
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

    if method == "POST" and endpoint == "/health/language/chat-dry-run":
        if not isinstance(payload, dict):
            return {
                "status": STATUS_FAILED,
                "reason": "invalid_dry_run_payload",
                "code": status_code,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        if str(payload.get("route_used") or "") != "POST /chat":
            return {
                "status": STATUS_FAILED,
                "reason": f"unexpected_route_used:{sanitize_output(str(payload.get('route_used')))}",
                "code": status_code,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        if payload.get("forced_french_runtime_detected") is True:
            return {
                "status": STATUS_WARNING,
                "reason": "forced_french_runtime_detected_in_dry_run",
                "code": status_code,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        if str(payload.get("profile_used") or "") != "fluxorca":
            return {
                "status": STATUS_WARNING,
                "reason": f"profile_expected_fluxorca_got:{sanitize_output(str(payload.get('profile_used')))}",
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

    critical = [r for r in results if r.get("tier") == TIER_CRITICAL]
    setup = [r for r in results if r.get("tier") == TIER_SETUP]
    setup_ok = len(setup) == 0 or all(r.get("status") == STATUS_GREEN for r in setup)
    critical_ok = len(critical) == 0 or all(r.get("status") == STATUS_GREEN for r in critical)

    prod_green = bool(setup_ok and critical_ok)

    return {
        "total": total,
        "green": green,
        "warnings": warnings,
        "failed": failed,
        "prod_green": prod_green,
        "setup_ok": setup_ok,
        "critical_ok": critical_ok,
        "slowest_endpoint": {
            "method": slowest.get("method"),
            "endpoint": slowest.get("endpoint"),
            "tier": slowest.get("tier"),
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
    payload: dict[str, Any] | None,
    tier: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> tuple[dict[str, Any], Any]:
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
            if method == "GET" or endpoint in (
                "/decision/arbitration/simulate",
                "/health/language/chat-dry-run",
                "/chat",
                "/api/chat",
                "/guest/session",
            ):
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
        tier=tier,
    )
    return (
        {
            "method": method,
            "endpoint": endpoint,
            "tier": tier,
            "status_code": status_code,
            "elapsed_ms": c["elapsed_ms"],
            "status": c["status"],
            "reason": c["reason"],
        },
        parsed,
    )


def _print_result(r: dict[str, Any]) -> None:
    print(
        f"[{r['status']}] [{r.get('tier')}] "
        f"{r['method']} {r['endpoint']} {r.get('status_code')} "
        f"{int(float(r.get('elapsed_ms') or 0.0))}ms {sanitize_output(r.get('reason') or '')}"
    )


_CHAT_BODY: dict[str, Any] = {
    "message": "Explain OpenChawn in English in one short sentence.",
    "project_name": "openchawn",
}


def run_smoke(*, base_url: str, fail_fast: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[tuple[str, str, dict[str, Any] | None, str]] = [
        ("POST", "/guest/session", {}, TIER_SETUP),
        ("GET", "/health", None, TIER_CRITICAL),
        ("GET", "/health/providers", None, TIER_IMPORTANT),
        ("GET", "/health/language", None, TIER_IMPORTANT),
        ("POST", "/chat", _CHAT_BODY, TIER_CRITICAL),
        ("POST", "/api/chat", dict(_CHAT_BODY), TIER_CRITICAL),
        (
            "POST",
            "/health/language/chat-dry-run",
            {
                "message": "hello how are you and what's your name?",
                "profile": "fluxorca",
            },
            TIER_OPTIONAL,
        ),
        ("GET", "/memory/semantic/health", None, TIER_OPTIONAL),
        ("GET", "/memory/semantic/stats", None, TIER_OPTIONAL),
        ("GET", "/memory/importance/health", None, TIER_OPTIONAL),
        ("GET", "/memory/importance/top", None, TIER_OPTIONAL),
        ("GET", "/memory/graph/stats", None, TIER_OPTIONAL),
        ("GET", "/memory/graph/hubs", None, TIER_OPTIONAL),
        ("GET", "/memory/temporal/snapshot", None, TIER_OPTIONAL),
        ("GET", "/memory/temporal/rising", None, TIER_OPTIONAL),
        ("GET", "/memory/contradictions/report", None, TIER_OPTIONAL),
        ("GET", "/decision/arbitration/report", None, TIER_OPTIONAL),
        ("GET", "/decision/arbitration/last", None, TIER_OPTIONAL),
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
            TIER_OPTIONAL,
        ),
    ]
    out: list[dict[str, Any]] = []
    with requests.Session() as s:
        for method, endpoint, payload, tier in checks:
            r, body = _check(s, base_url=base_url, method=method, endpoint=endpoint, payload=payload, tier=tier)
            if (
                endpoint == "/guest/session"
                and r.get("status") == STATUS_GREEN
                and isinstance(body, dict)
                and str(body.get("session_id") or "").strip()
            ):
                s.headers["X-Guest-Session"] = str(body["session_id"]).strip()
            out.append(r)
            _print_result(r)
            if fail_fast and r.get("status") == STATUS_FAILED:
                break
    summary = build_summary(out)
    print(
        f"[SUMMARY] prod_green={summary['prod_green']} setup_ok={summary['setup_ok']} "
        f"critical_ok={summary['critical_ok']} total={summary['total']} green={summary['green']} "
        f"warnings={summary['warnings']} failed={summary['failed']} avg_ms={summary['average_latency_ms']}"
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

    return 0 if summary.get("prod_green") else 1


if __name__ == "__main__":
    raise SystemExit(main())

