"""Structured 5 Why operational diagnostics for COCO — safe summaries only (no chain-of-thought)."""

from __future__ import annotations

import re
from typing import Any, Literal

# Marqueur test / audit : grep five_why_analysis_v1
FIVE_WHY_MARKER = "five_why_analysis_v1"
MAX_WHY_STEPS = 5

ConfidenceLevel = Literal["low", "medium", "high"]
IncidentClass = Literal[
    "backend_error",
    "railway_deploy",
    "provider_failure",
    "security_anomaly",
    "ui_bug",
    "memory_contradiction",
    "general",
]

_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(api[_-]?key|secret|password|token|authorization)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"sk-[a-zA-Z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"postgres(ql)?://\S+", re.IGNORECASE),
    re.compile(r"mysql://\S+", re.IGNORECASE),
    re.compile(r"redis://\S+", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"),
)

_FORBIDDEN_OUTPUT_FRAGMENTS = (
    "chain of thought",
    "chain-of-thought",
    "hidden prompt",
    "system prompt",
    "raw reasoning",
)


def sanitize_diagnostic_text(text: str | None, *, max_len: int = 2000) -> str:
    """Strip secrets and trim — safe for operator-facing diagnosis."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""
    for pattern in _SENSITIVE_PATTERNS:
        raw = pattern.sub("[redacted]", raw)
    if len(raw) > max_len:
        raw = raw[: max_len - 3].rstrip() + "..."
    return raw


def _normalize_risk_level(risk_level: str | None) -> str:
    level = (risk_level or "medium").strip().lower()
    if level in ("low", "medium", "high", "critical"):
        return "critical" if level == "critical" else level
    return "medium"


def _classify_incident(problem: str, context: str, logs: str) -> IncidentClass:
    blob = f"{problem} {context} {logs}".lower()
    if any(
        k in blob
        for k in (
            "security",
            "unauthorized",
            "forbidden",
            "injection",
            "xss",
            "csrf",
            "secret leak",
            "credential",
            "breach",
        )
    ):
        return "security_anomaly"
    if any(
        k in blob
        for k in (
            "contradiction",
            "memory conflict",
            "conflicting memory",
            "concept merge",
            "memory contradiction",
        )
    ):
        return "memory_contradiction"
    if any(
        k in blob
        for k in (
            "railway",
            "deploy",
            "deployment",
            "build failed",
            "container",
            "ephemeral",
            "redeploy",
        )
    ):
        return "railway_deploy"
    if any(
        k in blob
        for k in (
            "provider",
            "openai",
            "deepseek",
            "mistral",
            "429",
            "502",
            "503",
            "timeout",
            "api error",
            "rate limit",
            "llm",
        )
    ):
        return "provider_failure"
    if any(
        k in blob
        for k in (
            "ui",
            "button",
            "mobile",
            "composer",
            "safari",
            "cursor",
            "mic",
            "frontend",
            "chip",
        )
    ):
        return "ui_bug"
    if any(
        k in blob
        for k in (
            "exception",
            "traceback",
            "500",
            "internal server",
            "backend",
            "handler",
            "fastapi",
        )
    ):
        return "backend_error"
    return "general"


def _confidence_level(
    *,
    context: str,
    logs_summary: str,
    risk_level: str,
    incident: IncidentClass,
) -> ConfidenceLevel:
    if not context and not logs_summary:
        return "low"
    score = 0
    if context:
        score += 1
    if logs_summary:
        score += 1
    if incident != "general":
        score += 1
    if risk_level in ("high", "critical") and logs_summary:
        score += 1
    if score >= 3:
        return "high"
    if score >= 1:
        return "medium"
    return "low"


def _templates(incident: IncidentClass) -> dict[str, Any]:
    """Operational why templates — short engineer-facing steps, not private reasoning."""
    catalog: dict[IncidentClass, dict[str, Any]] = {
        "backend_error": {
            "why": [
                "User-visible failure or HTTP 5xx returned from an API handler.",
                "Unhandled exception or invalid assumption inside request handling.",
                "Missing validation, race, or dependency failure under load.",
                "Insufficient error boundaries or observability on the failing path.",
            ],
            "root": "A backend code path fails without graceful degradation for this input or state.",
            "fix": "Reproduce with the same route and payload; add guards, fix the exception source, and return a safe client error.",
            "prevention": [
                "Add regression test for the failing route.",
                "Log structured error codes without secrets.",
                "Verify health and smoke tests after deploy.",
            ],
        },
        "railway_deploy": {
            "why": [
                "Service unhealthy or wrong build running after a deploy.",
                "Branch, start command, or env vars do not match the intended environment.",
                "Ephemeral disk or missing volume for local persistence.",
                "Database or memory URL not wired for production durability.",
            ],
            "root": "Deployment configuration or runtime environment does not match the intended production contract.",
            "fix": "Confirm deployed git commit, env template, and persistent services; redeploy after correcting MEMORY_BACKEND, DATABASE_URL, and branch linkage.",
            "prevention": [
                "Check /__runtime git_commit after each deploy.",
                "Keep staging and production variable sets isolated.",
                "Use Postgres for durable fractal memory on Railway.",
            ],
        },
        "provider_failure": {
            "why": [
                "Chat request fails at the LLM gateway or provider HTTP layer.",
                "Provider unavailable, rate-limited, or rejecting the model or region.",
                "API key, base URL, or model name mismatch for this environment.",
                "Fallback chain exhausted without a healthy provider.",
            ],
            "root": "No healthy LLM provider is reachable with valid configuration for this deployment.",
            "fix": "Verify provider health endpoint, keys (via platform UI only), model IDs, and fallback order; temporarily route to a known-good provider.",
            "prevention": [
                "Monitor provider availability flags in /health.",
                "Alert on sustained 429/5xx from gateway.",
                "Document primary and fallback providers per environment.",
            ],
        },
        "security_anomaly": {
            "why": [
                "Unexpected auth failure, policy violation, or suspicious access pattern detected.",
                "Input or output may expose secrets or bypass intended access controls.",
                "Misconfigured CORS, tokens, or owner-only routes.",
                "Repeated probes or abnormal client behavior.",
            ],
            "root": "A security control gap or active misuse attempt is producing abnormal signals.",
            "fix": "Rotate affected credentials via platform UI, tighten CORS and rate limits, audit logs for scope, and block abusive IPs if needed.",
            "prevention": [
                "Never log raw tokens or API keys.",
                "Run periodic secret scans and security checklist.",
                "Keep owner and guest paths explicitly separated in tests.",
            ],
        },
        "ui_bug": {
            "why": [
                "User action in the composer or COCO shell does not match expected behavior.",
                "Event handler, state flag, or mobile layout differs from desktop.",
                "Browser API (e.g. speech) lifecycle ends without updating draft state.",
                "Duplicate handlers or race between UI state and network send.",
            ],
            "root": "Client-side state or handler wiring does not preserve the user draft through the interaction.",
            "fix": "Reproduce on target viewport; fix state flags and ensure only the send button submits; add UI regression test.",
            "prevention": [
                "Test mobile Safari for composer and mic flows.",
                "Use event delegation with explicit draft-only voice rules.",
                "Avoid auto-send from speech callbacks.",
            ],
        },
        "memory_contradiction": {
            "why": [
                "Retrieved memories disagree on facts (e.g. provider or deployment).",
                "New exchange conflicts with an existing concept or system memory.",
                "Contradiction flags block injection for one layer but not another.",
                "Stale session memory competes with long-term project or system memory.",
            ],
            "root": "Fractal memory layers contain conflicting authoritative statements for the same topic.",
            "fix": "Review contradicted entries via memory tools; archive or neutralize stale facts; write a single canonical system/project memory.",
            "prevention": [
                "Prefer system memory for deployment truths.",
                "Run contradiction review after provider policy changes.",
                "Avoid duplicating provider rules in session-only memory.",
            ],
        },
        "general": {
            "why": [
                "Observed behavior differs from expected operational outcome.",
                "Insufficient context to isolate a single subsystem.",
                "Intermittent or environment-specific trigger not yet confirmed.",
                "Monitoring or logs do not yet pinpoint the failing component.",
            ],
            "root": "Root cause not isolated — more scoped evidence is needed.",
            "fix": "Gather route, timestamp, environment, and sanitized logs; rerun analysis with narrower context.",
            "prevention": [
                "Capture minimal repro steps.",
                "Attach sanitized logs_summary and risk_level.",
                "Re-run 5 Why after deploy or config change.",
            ],
        },
    }
    return catalog[incident]


def _build_why_chain(incident: IncidentClass, symptom: str) -> list[str]:
    template = _templates(incident)
    chain: list[str] = []
    for step in template["why"]:
        if len(chain) >= MAX_WHY_STEPS:
            break
        chain.append(step)
    if len(chain) < MAX_WHY_STEPS and symptom:
        chain.append(f"Symptom anchor: {symptom[:160].rstrip('.')}.")
    return chain[:MAX_WHY_STEPS]


def _fallback_diagnosis(risk_level: str) -> dict[str, Any]:
    return {
        "analysis_marker": FIVE_WHY_MARKER,
        "symptom": "No observable problem statement provided.",
        "why_chain": [
            "Operator report missing or empty.",
            "Cannot classify incident without observed_problem.",
            "Add a short symptom description and retry.",
        ],
        "probable_root_cause": "Insufficient input — observed_problem is required.",
        "recommended_fix": "Supply observed_problem, optional context and logs_summary (sanitized), then re-run analysis.",
        "prevention_checklist": [
            "Always pass a one-line observed_problem.",
            "Include environment (staging vs production) in context.",
            "Paste sanitized log excerpts only.",
        ],
        "confidence_level": "low",
    }


def analyze_five_why(
    *,
    observed_problem: str,
    context: str = "",
    logs_summary: str = "",
    risk_level: str | None = None,
) -> dict[str, Any]:
    """
    Produce a safe structured 5 Why diagnosis for COCO and operators.

    Returns operational fields only — no hidden prompts, secrets, or chain-of-thought.
    """
    symptom = sanitize_diagnostic_text(observed_problem, max_len=500)
    ctx = sanitize_diagnostic_text(context, max_len=1200)
    logs = sanitize_diagnostic_text(logs_summary, max_len=1200)
    risk = _normalize_risk_level(risk_level)

    if not symptom:
        return _fallback_diagnosis(risk)

    incident = _classify_incident(symptom, ctx, logs)
    template = _templates(incident)
    why_chain = _build_why_chain(incident, symptom)
    confidence = _confidence_level(
        context=ctx,
        logs_summary=logs,
        risk_level=risk,
        incident=incident,
    )

    result = {
        "analysis_marker": FIVE_WHY_MARKER,
        "symptom": symptom,
        "why_chain": why_chain,
        "probable_root_cause": str(template["root"]),
        "recommended_fix": str(template["fix"]),
        "prevention_checklist": list(template["prevention"]),
        "confidence_level": confidence,
    }

    # Final safety pass on string fields
    blob = " ".join(
        [result["symptom"]]
        + result["why_chain"]
        + [result["probable_root_cause"], result["recommended_fix"]]
        + result["prevention_checklist"]
    ).lower()
    for forbidden in _FORBIDDEN_OUTPUT_FRAGMENTS:
        if forbidden in blob:
            result["recommended_fix"] = (
                "Review sanitized logs and configuration; escalate with operator evidence."
            )
            break

    return result


def format_five_why_report(diagnosis: dict[str, Any]) -> str:
    """Plain-text engineer report — safe to show in chat or ops notes."""
    lines = [
        f"Symptom: {diagnosis.get('symptom', '')}",
        "Why chain:",
    ]
    for i, why in enumerate(diagnosis.get("why_chain") or [], start=1):
        lines.append(f"  {i}. {why}")
    lines.extend(
        [
            f"Probable root cause: {diagnosis.get('probable_root_cause', '')}",
            f"Recommended fix: {diagnosis.get('recommended_fix', '')}",
            f"Confidence: {diagnosis.get('confidence_level', 'low')}",
            "Prevention:",
        ]
    )
    for item in diagnosis.get("prevention_checklist") or []:
        lines.append(f"  - {item}")
    return "\n".join(lines)
