"""
Decision Arbitration Layer V11.6.

Arbitre plusieurs options de decision sans appel LLM.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.memory import fractal_memory as fm

_LOCK = Lock()
_LAST_ARBITRATION: dict[str, Any] = {"status": "empty", "options": []}

_ALLOWED_STRATEGIES = {
    "provider_strategy",
    "deployment_strategy",
    "memory_strategy",
    "security_strategy",
    "cost_strategy",
    "architecture_strategy",
    "product_strategy",
    "unknown",
}

_ALLOWED_STATUSES = {
    "selected",
    "rejected",
    "tie_needs_review",
    "blocked_by_risk",
    "no_viable_option",
    "needs_human_review",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_strategy(title: str, decision_type: str = "") -> str:
    dt = str(decision_type or "").strip().lower()
    if dt in _ALLOWED_STRATEGIES:
        return dt
    t = str(title or "").lower()
    if any(k in t for k in ("provider", "deepseek", "openai", "openrouter", "ollama")):
        return "provider_strategy"
    if any(k in t for k in ("deploy", "railway", "production", "infra")):
        return "deployment_strategy"
    if any(k in t for k in ("memory", "retrieval", "faiss", "compression")):
        return "memory_strategy"
    if any(k in t for k in ("security", "secret", "token", "api key", "apikey", "auth", "tls")):
        return "security_strategy"
    if any(k in t for k in ("cost", "cheap", "pricing", "budget")):
        return "cost_strategy"
    if any(k in t for k in ("architecture", "service", "module", "dependency")):
        return "architecture_strategy"
    if any(k in t for k in ("product", "feature", "user")):
        return "product_strategy"
    return "unknown"


def build_arbitration_options(
    *,
    project: str = "",
    decision_type: str = "",
    options: list[dict[str, Any]] | None = None,
    entries: list[dict] | None = None,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = entries if isinstance(entries, list) else fm.entries_snapshot_for_tests()
    by_id = {str(e.get("id") or ""): e for e in rows if e.get("id")}
    built: list[dict[str, Any]] = []
    for i, raw in enumerate(list(options or []), start=1):
        mem_ids = [str(x) for x in (raw.get("source_memory_ids") or []) if str(x).strip()]
        src = [by_id[mid] for mid in mem_ids if mid in by_id]
        title_raw = str(raw.get("title") or f"Option {i}").strip()[:260]
        title = "[REDACTED_SECRET]" if fm._contains_sensitive_text(title_raw) else title_raw  # noqa: SLF001
        strategy = _infer_strategy(title, decision_type)
        built.append(
            {
                "option_id": str(raw.get("option_id") or f"opt_{i}"),
                "title": title,
                "source_memory_ids": mem_ids,
                "strategy_type": strategy,
                "project": str(project or ""),
                "_source_memories": src,
                "_context": context or {},
            }
        )
    return built


def score_decision_option(option: dict[str, Any]) -> dict[str, Any]:
    src = list(option.get("_source_memories") or [])
    ctx = option.get("_context") if isinstance(option.get("_context"), dict) else {}
    if not src:
        src = []
    n = max(1, len(src))
    avg_imp = sum(float(e.get("importance_score") or 0.0) for e in src) / n
    avg_cen = sum(float(e.get("graph_centrality") or 0.0) for e in src) / n
    avg_ltv = sum(float(e.get("long_term_value") or 0.0) for e in src) / n
    avg_conf = sum(float(e.get("resolution_confidence") or 0.0) for e in src) / n
    unresolved = sum(1 for e in src if str(e.get("contradiction_resolution_status") or "") in ("unresolved", "conflict_active"))
    deprecated = sum(1 for e in src if str(e.get("contradiction_resolution_status") or "") in ("deprecated", "superseded"))
    needs_review = any(bool(e.get("human_review_required")) or str(e.get("contradiction_resolution_status") or "") == "needs_human_review" for e in src)
    rising = sum(1 for e in src if str(e.get("temporal_status") or "") in ("rising", "stable"))
    trend = sum(float(e.get("trend_score") or 0.0) for e in src) / n

    confidence = max(0.0, min(1.0, avg_imp * 0.52 + avg_conf * 0.2 + max(0.0, trend) * 0.18 + (0.06 if rising >= 1 else 0.0)))
    graph_score = max(0.0, min(1.0, min(0.9, avg_cen * 0.06)))
    temporal_score = max(0.0, min(1.0, max(0.0, trend) * 0.7 + min(0.3, rising * 0.09)))
    stability_score = max(0.0, min(1.0, avg_ltv * 0.72 + temporal_score * 0.2 + graph_score * 0.08))
    contradiction_penalty = min(1.0, unresolved * 0.4 + deprecated * 0.22)

    title_l = str(option.get("title") or "").lower()
    cost_score = 0.55
    if "deepseek" in title_l:
        cost_score = 0.84
    elif "openai" in title_l:
        cost_score = 0.48
    elif "fallback" in title_l:
        cost_score = 0.58
    elif any(k in title_l for k in ("cheap", "cost", "budget")):
        cost_score = 0.8
    risk = max(0.0, min(1.0, contradiction_penalty * 0.58 + (1.0 - stability_score) * 0.22 + (0.28 if needs_review else 0.0) + float(ctx.get("context_risk") or 0.0) * 0.18))

    final = (
        confidence * 0.30
        + stability_score * 0.19
        + graph_score * 0.12
        + temporal_score * 0.13
        + cost_score * 0.14
        + float(ctx.get("context_confidence") or 0.0) * 0.12
        - contradiction_penalty * 0.36
        - risk * 0.24
    )
    if str(option.get("strategy_type") or "") == "security_strategy" and ("secret" in title_l or "token" in title_l or "api key" in title_l):
        needs_review = True
    status = "rejected"
    rejection = ""
    if needs_review:
        status = "needs_human_review"
        rejection = "security_or_sensitive_requires_human_review"
    elif risk >= 0.82:
        status = "blocked_by_risk"
        rejection = "risk_too_high"
    elif deprecated >= max(1, n):
        status = "rejected"
        rejection = "deprecated_or_superseded_sources"
    return {
        **option,
        "confidence_score": round(confidence, 4),
        "risk_score": round(risk, 4),
        "stability_score": round(stability_score, 4),
        "cost_score": round(cost_score, 4),
        "temporal_score": round(temporal_score, 4),
        "graph_score": round(graph_score, 4),
        "contradiction_penalty": round(contradiction_penalty, 4),
        "final_score": round(final, 4),
        "selected": False,
        "status": status if status in _ALLOWED_STATUSES else "rejected",
        "rejection_reason": rejection,
        "arbitration_explanation": "",
    }


def compare_decision_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(options, key=lambda o: float(o.get("final_score") or -999.0), reverse=True)


def explain_arbitration(option: dict[str, Any]) -> str:
    return (
        f"confidence={float(option.get('confidence_score') or 0.0):.2f};"
        f"risk={float(option.get('risk_score') or 0.0):.2f};"
        f"stability={float(option.get('stability_score') or 0.0):.2f};"
        f"cost={float(option.get('cost_score') or 0.0):.2f};"
        f"temporal={float(option.get('temporal_score') or 0.0):.2f};"
        f"graph={float(option.get('graph_score') or 0.0):.2f};"
        f"penalty={float(option.get('contradiction_penalty') or 0.0):.2f}"
    )


def arbitrate_decision(
    *,
    project: str = "",
    decision_type: str = "",
    options: list[dict[str, Any]] | None = None,
    entries: list[dict] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global _LAST_ARBITRATION
    built = build_arbitration_options(project=project, decision_type=decision_type, options=options, entries=entries, context=context)
    if not built:
        rep = {"status": "no_viable_option", "selected_option": None, "options": []}
        with _LOCK:
            global _LAST_ARBITRATION
            _LAST_ARBITRATION = copy.deepcopy(rep)
        return rep
    scored = [score_decision_option(x) for x in built]
    ranked = compare_decision_options(scored)
    viable = [
        x
        for x in ranked
        if str(x.get("status")) not in ("needs_human_review", "blocked_by_risk")
        and not str(x.get("rejection_reason") or "").strip()
    ]
    selected = None
    status = "no_viable_option"
    if viable:
        top = viable[0]
        if len(viable) > 1 and abs(float(viable[0].get("final_score") or 0.0) - float(viable[1].get("final_score") or 0.0)) <= 0.03:
            top["status"] = "tie_needs_review"
            top["rejection_reason"] = "scores_too_close"
            status = "tie_needs_review"
        elif float(top.get("risk_score") or 0.0) >= 0.82:
            top["status"] = "blocked_by_risk"
            top["rejection_reason"] = "risk_too_high"
            status = "blocked_by_risk"
        else:
            top["selected"] = True
            top["status"] = "selected"
            status = "selected"
            selected = top
    for o in ranked:
        if o is selected:
            o["arbitration_explanation"] = explain_arbitration(o)
            continue
        if not o.get("rejection_reason"):
            if str(o.get("status")) == "needs_human_review":
                o["rejection_reason"] = "human_review_required"
            elif str(o.get("status")) == "blocked_by_risk":
                o["rejection_reason"] = "risk_too_high"
            else:
                o["status"] = "rejected"
                o["rejection_reason"] = "lower_final_score"
        o["arbitration_explanation"] = explain_arbitration(o)
    rep = build_arbitration_report(ranked, selected_option=selected, status=status)
    with _LOCK:
        _LAST_ARBITRATION = copy.deepcopy(rep)
    return rep


def build_arbitration_report(options: list[dict[str, Any]], *, selected_option: dict[str, Any] | None, status: str) -> dict[str, Any]:
    safe = []
    for o in options:
        d = {k: v for k, v in o.items() if not str(k).startswith("_")}
        safe.append(d)
    return {
        "status": status if status in _ALLOWED_STATUSES else "rejected",
        "selected_option": {k: v for k, v in dict(selected_option or {}).items() if not str(k).startswith("_")} if selected_option else None,
        "options": safe,
        "generated_at": _now_iso(),
    }


def get_last_arbitration() -> dict[str, Any]:
    with _LOCK:
        return copy.deepcopy(_LAST_ARBITRATION)


def clear_arbitration_for_tests() -> None:
    with _LOCK:
        global _LAST_ARBITRATION
        _LAST_ARBITRATION = {"status": "empty", "options": []}

