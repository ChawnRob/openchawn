"""5 Why root-cause analysis — safe operational diagnostics."""

from __future__ import annotations

import json

import pytest

from app.core.five_why_analysis import (
    FIVE_WHY_MARKER,
    MAX_WHY_STEPS,
    analyze_five_why,
    format_five_why_report,
    sanitize_diagnostic_text,
)


def test_normal_bug_analysis_backend():
    out = analyze_five_why(
        observed_problem="POST /chat returns HTTP 500 after deploy",
        context="Railway staging, FastAPI handler",
        logs_summary="Traceback in chat handler, ValueError on empty provider response",
        risk_level="medium",
    )
    assert out["analysis_marker"] == FIVE_WHY_MARKER
    assert "500" in out["symptom"] or "POST" in out["symptom"]
    assert 1 <= len(out["why_chain"]) <= MAX_WHY_STEPS
    assert out["probable_root_cause"]
    assert out["recommended_fix"]
    assert len(out["prevention_checklist"]) >= 2
    assert out["confidence_level"] in ("low", "medium", "high")


def test_security_incident_analysis():
    out = analyze_five_why(
        observed_problem="Repeated unauthorized access to owner routes",
        context="security anomaly, CORS misconfiguration suspected",
        logs_summary="401 on /owner, suspicious IP pattern",
        risk_level="high",
    )
    blob = json.dumps(out).lower()
    assert "security" in blob or "credential" in blob or "cors" in blob
    assert out["confidence_level"] in ("medium", "high")
    assert len(out["why_chain"]) <= MAX_WHY_STEPS


def test_no_secret_leakage():
    raw = (
        "API_KEY=sk-live-abcdef1234567890 password=supersecret "
        "postgres://user:pass@host/db Bearer eyJhbGciOiJIUzI1NiJ9"
    )
    sanitized = sanitize_diagnostic_text(raw)
    assert "sk-live" not in sanitized
    assert "supersecret" not in sanitized
    assert "postgres://" not in sanitized
    assert "eyJhbGci" not in sanitized
    assert "[redacted]" in sanitized

    out = analyze_five_why(
        observed_problem=f"Provider failure with logs {raw}",
        context="",
        logs_summary=raw,
    )
    dumped = json.dumps(out)
    assert "sk-live" not in dumped
    assert "supersecret" not in dumped
    assert "postgres://" not in dumped
    assert "hidden prompt" not in dumped.lower()
    assert "chain of thought" not in dumped.lower()


def test_max_five_why_steps():
    out = analyze_five_why(
        observed_problem="Memory contradiction on DeepSeek vs Ollama provider policy",
        context="fractal memory contradiction_detected flags in session and system layers",
        logs_summary="concept merge conflict railway production",
        risk_level="low",
    )
    assert len(out["why_chain"]) <= MAX_WHY_STEPS


def test_graceful_fallback_missing_context():
    out = analyze_five_why(
        observed_problem="",
        context="",
        logs_summary="",
    )
    assert out["confidence_level"] == "low"
    assert "observed_problem" in out["probable_root_cause"].lower() or "insufficient" in out[
        "probable_root_cause"
    ].lower()
    assert out["why_chain"]


def test_provider_failure_class():
    out = analyze_five_why(
        observed_problem="Chat fails with provider timeout 503",
        context="DeepSeek primary, Railway production",
        logs_summary="gateway exhausted fallbacks",
    )
    low = json.dumps(out).lower()
    assert "provider" in low or "llm" in low or "fallback" in low


def test_format_report_readable():
    out = analyze_five_why(
        observed_problem="Mobile mic clears composer draft",
        context="ui bug safari",
        logs_summary="",
    )
    report = format_five_why_report(out)
    assert "Symptom:" in report
    assert "Why chain:" in report
    assert "Prevention:" in report
