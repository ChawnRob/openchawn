"""
Memory Importance Scoring Layer V11.6.

Heuristiques locales uniquement:
- pas de LLM
- pas d'embeddings obligatoires
- pas de vector DB obligatoire
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from app.memory import fractal_memory as fm

_NOISE_WORDS = ("ok", "merci", "thanks", "salut", "hello", "hi", "daccord", "👍")
_STRATEGIC_WORDS = (
    "architecture",
    "provider",
    "deepseek",
    "railway",
    "security",
    "sécurité",
    "memory",
    "mémoire",
    "index",
    "retrieval",
    "consolidation",
    "compression",
    "postgres",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text_bucket(entry: dict) -> str:
    return " ".join(
        [
            str(entry.get("summary") or ""),
            str(entry.get("user_message") or ""),
            str(entry.get("assistant_response") or ""),
            " ".join([str(t) for t in (entry.get("tags") or [])]),
        ]
    ).strip()


def _is_sensitive(entry: dict) -> bool:
    txt = _text_bucket(entry)
    if fm._contains_sensitive_text(txt):  # noqa: SLF001
        return True
    if re.search(r"\bapi[_-]?key\s*=\s*\S+|\bsk-[A-Za-z0-9_-]{8,}\b|\bBearer\s+[A-Za-z0-9._-]{8,}\b", txt):
        return True
    md = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    return bool(md.get("secret") or md.get("contains_secret") or md.get("has_token"))


def compute_recurrence_score(entry: dict) -> float:
    md = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    access = int(entry.get("access_count") or 0)
    hits = int(md.get("retrieval_hits") or 0)
    merges = int(md.get("merge_count") or 0)
    linked = 1 if str(md.get("linked_concept_id") or "").strip() else 0
    score = min(1.0, access * 0.08 + hits * 0.06 + merges * 0.04 + linked * 0.08)
    return round(max(0.0, score), 4)


def compute_semantic_density(entry: dict) -> float:
    txt = _text_bucket(entry).lower()
    words = [w for w in txt.replace("\n", " ").split(" ") if w.strip()]
    uniq = len(set(words))
    total = max(1, len(words))
    uniq_ratio = min(1.0, uniq / total)
    strategic_hits = sum(1 for w in _STRATEGIC_WORDS if w in txt)
    score = min(1.0, uniq_ratio * 0.55 + strategic_hits * 0.1)
    return round(max(0.0, score), 4)


def compute_contradiction_risk(entry: dict) -> float:
    risk = 0.0
    if bool(entry.get("contradiction_detected")):
        risk += 0.65
    md = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    if str(md.get("contradiction_status") or "").strip().lower() in ("open", "unresolved"):
        risk += 0.2
    txt = _text_bucket(entry).lower()
    if "ollama" in txt and any(x in txt for x in ("prod", "production", "principal", "default")):
        risk += 0.15
    return round(min(1.0, risk), 4)


def compute_long_term_value(entry: dict) -> float:
    md = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    mt = str(entry.get("memory_type") or "").lower()
    level = str(entry.get("memory_level") or "").lower()
    merges = int(md.get("merge_count") or 0)
    linked = 1 if str(md.get("linked_concept_id") or "").strip() else 0
    compressed = 1 if mt == "compressed" else 0
    system = 1 if mt == "system" else 0
    concept = 1 if level == "concept_memory" else 0
    strategic_hits = sum(1 for w in _STRATEGIC_WORDS if w in _text_bucket(entry).lower())
    graph_degree = int(entry.get("graph_degree") or 0)
    graph_centrality = float(entry.get("graph_centrality") or 0.0)
    momentum = float(entry.get("momentum_score") or 0.0)
    score = min(
        1.0,
        system * 0.35
        + compressed * 0.22
        + concept * 0.16
        + linked * 0.12
        + min(0.2, merges * 0.03)
        + min(0.25, strategic_hits * 0.06)
        + min(0.14, graph_degree * 0.01)
        + min(0.2, graph_centrality * 0.03)
        + min(0.14, max(0.0, momentum) * 0.45),
    )
    if str(entry.get("contradiction_resolution_status") or "") in ("deprecated", "superseded"):
        score *= 0.55
    return round(max(0.0, score), 4)


def _recency_score(entry: dict) -> float:
    ts = str(entry.get("timestamp") or entry.get("created_at") or "").replace("Z", "+00:00")
    if not ts:
        return 0.45
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400.0)
        return max(0.05, min(1.0, 1.0 - age_days / 40.0))
    except Exception:
        return 0.45


def explain_importance_score(entry: dict, breakdown: dict[str, float]) -> str:
    txt = _text_bucket(entry).lower()
    reasons: list[str] = []
    if breakdown["base_type"] >= 0.55:
        reasons.append("memory_type structurant")
    if breakdown["strategic_signal"] >= 0.18:
        reasons.append("contenu technique/architecture")
    if breakdown["recurrence_score"] >= 0.28:
        reasons.append("réutilisation récurrente")
    if breakdown["long_term_value"] >= 0.45:
        reasons.append("valeur long-terme élevée")
    if breakdown["contradiction_risk"] >= 0.55:
        reasons.append("risque contradiction élevé")
    if any(w in txt for w in _NOISE_WORDS) and len(txt) < 32:
        reasons.append("message bruit faible")
    if not reasons:
        reasons.append("signal moyen équilibré")
    return "; ".join(reasons)[:300]


def compute_memory_importance(entry: dict, entries: list[dict] | None = None) -> dict[str, Any]:
    e = fm._ensure_entry_defaults(dict(entry))  # noqa: SLF001
    md = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
    txt = _text_bucket(e).lower()

    if _is_sensitive(e):
        return {
            "importance_score": 0.0,
            "recurrence_score": 0.0,
            "semantic_density": 0.0,
            "contradiction_risk": 1.0 if bool(e.get("contradiction_detected")) else 0.6,
            "long_term_value": 0.0,
            "importance_explanation": "contenu sensible: importance forcée à 0 et non indexable",
            "importance_updated_at": _now_iso(),
            "indexable": False,
        }

    mt = str(e.get("memory_type") or "").lower()
    lvl = str(e.get("memory_level") or "").lower()
    base_type = 0.18
    if mt == "system":
        base_type = 0.8
    elif mt == "compressed":
        base_type = 0.62
    elif mt == "project":
        base_type = 0.46
    elif mt == "user":
        base_type = 0.42
    elif mt == "session":
        base_type = 0.26
    if lvl == "concept_memory":
        base_type += 0.08

    recurrence = compute_recurrence_score(e)
    semantic_density = compute_semantic_density(e)
    contradiction_risk = compute_contradiction_risk(e)
    long_term = compute_long_term_value(e)
    recency = _recency_score(e)

    strategic_signal = min(0.35, sum(0.06 for w in _STRATEGIC_WORDS if w in txt))
    banal = any(w in txt for w in _NOISE_WORDS) and len(txt) < 44
    banal_penalty = 0.28 if banal else 0.0

    compressed_into = str(md.get("compressed_into") or "").strip()
    duplicate_penalty = 0.18 if compressed_into and mt != "compressed" else 0.0
    archived_penalty = 0.14 if str(e.get("lifecycle_status") or "") == fm.MEMORY_LIFECYCLE_ARCHIVED else 0.0

    raw_score = (
        base_type * 0.32
        + recurrence * 0.18
        + semantic_density * 0.14
        + long_term * 0.26
        + recency * 0.1
        + strategic_signal
        - contradiction_risk * 0.18
        - banal_penalty
        - duplicate_penalty
        - archived_penalty
    )
    importance = round(max(0.0, min(1.0, raw_score)), 4)

    br = {
        "base_type": round(base_type, 4),
        "recurrence_score": recurrence,
        "semantic_density": semantic_density,
        "long_term_value": long_term,
        "recency_score": round(recency, 4),
        "strategic_signal": round(strategic_signal, 4),
        "contradiction_risk": contradiction_risk,
    }
    explanation = explain_importance_score(e, br)
    return {
        "importance_score": importance,
        "recurrence_score": recurrence,
        "semantic_density": semantic_density,
        "contradiction_risk": contradiction_risk,
        "long_term_value": long_term,
        "importance_explanation": explanation,
        "importance_updated_at": _now_iso(),
        "indexable": True,
    }


def refresh_importance_scores(entries: list[dict] | None = None, *, persist: bool = True) -> dict[str, Any]:
    owned = entries is None
    if owned:
        with fm._STORE_LOCK:  # noqa: SLF001
            rows = [fm._ensure_entry_defaults(dict(e)) for e in fm._load_entries()]  # noqa: SLF001
            updated = 0
            for i, e in enumerate(rows):
                imp = compute_memory_importance(e, rows)
                e.update(imp)
                rows[i] = e
                updated += 1
            if persist:
                fm._save_entries(rows)  # noqa: SLF001
            return {"status": "ok", "updated": updated, "persisted": bool(persist), "owned_store": True}

    rows = [fm._ensure_entry_defaults(dict(e)) for e in (entries or [])]  # noqa: SLF001
    updated = 0
    for i, e in enumerate(rows):
        imp = compute_memory_importance(e, rows)
        e.update(imp)
        rows[i] = e
        updated += 1
    if isinstance(entries, list):
        entries[:] = rows
    return {"status": "ok", "updated": updated, "persisted": False, "owned_store": False}

