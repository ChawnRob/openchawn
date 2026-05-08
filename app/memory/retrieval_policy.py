"""
Retrieval Policy Layer V11.6 — adapte le retrieval mémoire à l’état cognitif OpenChawn.
Heuristiques locales uniquement : pas d’embeddings, FAISS, vector DB ni LLM.
"""

from __future__ import annotations

import copy
from threading import Lock
from typing import Any

from app.cognition.cognitive_state_engine import ALLOWED_STATES
from app.memory.memory_timeline import sanitize_timeline_text

_LAST_POLICY_LOCK = Lock()
_LAST_POLICY: dict[str, Any] = {"status": "empty"}

DEFAULT_LAYER_LIMITS = {"system": 2, "user": 2, "project": 3, "session": 5}


def policy_for_cognitive_state(
    state: str,
    *,
    pressure_score: float = 30.0,
    contradiction_level: str = "low",
) -> dict[str, Any]:
    """
    Construit une policy à partir du label d’état cognitif (+ signaux optionnels).
    Champs sortants alignés sur le contrat Retrieval Policy V11.6.
    """
    st = (state or "stable").strip().lower()
    if st not in ALLOWED_STATES:
        st = "stable"

    pressure = float(pressure_score or 0.0)
    contra = str(contradiction_level or "low").lower()

    # Valeurs par défaut « retrieval normal »
    policy = {
        "state_resolved": st,
        "max_system": DEFAULT_LAYER_LIMITS["system"],
        "max_user": DEFAULT_LAYER_LIMITS["user"],
        "max_project": DEFAULT_LAYER_LIMITS["project"],
        "max_session": DEFAULT_LAYER_LIMITS["session"],
        "diversity_level": 0.48,
        "contradiction_mode": "off",
        "compression_level": "none",
        "conflict_penalty_scale": 1.0,
        "confidence_scale": 1.0,
        "importance_floor_session": 0.0,
        "max_decay_session_keep": 100.0,
    }

    if st == "focused":
        policy.update(
            max_project=min(6, DEFAULT_LAYER_LIMITS["project"] + 2),
            max_session=max(2, DEFAULT_LAYER_LIMITS["session"] - 2),
            diversity_level=0.32,
            contradiction_mode="off",
            compression_level="light",
            conflict_penalty_scale=1.06,
            confidence_scale=1.02,
        )
    elif st == "exploring":
        policy.update(
            max_project=min(7, DEFAULT_LAYER_LIMITS["project"] + 2),
            max_session=min(9, DEFAULT_LAYER_LIMITS["session"] + 4),
            max_user=min(4, DEFAULT_LAYER_LIMITS["user"] + 2),
            diversity_level=0.86,
            contradiction_mode="off",
            compression_level="none",
            conflict_penalty_scale=1.02,
            confidence_scale=0.95,
        )
    elif st == "contradicted":
        policy.update(
            max_project=min(6, DEFAULT_LAYER_LIMITS["project"] + 1),
            max_session=min(8, DEFAULT_LAYER_LIMITS["session"] + 2),
            diversity_level=0.58,
            contradiction_mode="include_flagged",
            compression_level="light",
            conflict_penalty_scale=1.38 if contra != "low" else 1.28,
            confidence_scale=0.87,
        )
    elif st == "overloaded":
        policy.update(
            max_system=2,
            max_user=max(0, DEFAULT_LAYER_LIMITS["user"] - 1),
            max_project=max(1, DEFAULT_LAYER_LIMITS["project"] - 1),
            max_session=max(1, DEFAULT_LAYER_LIMITS["session"] - 3),
            diversity_level=0.22,
            contradiction_mode="off",
            compression_level="aggressive",
            conflict_penalty_scale=1.14,
            confidence_scale=0.84,
        )
    elif st == "uncertain":
        policy.update(
            max_session=max(2, DEFAULT_LAYER_LIMITS["session"] - 1),
            diversity_level=0.42,
            contradiction_mode="off",
            compression_level="light",
            conflict_penalty_scale=1.1,
            confidence_scale=0.89,
            importance_floor_session=0.06,
        )
    elif st in ("stable", "high_confidence"):
        policy.update(
            diversity_level=0.36,
            contradiction_mode="off",
            compression_level="light",
            conflict_penalty_scale=0.98 if st == "high_confidence" else 1.0,
            confidence_scale=1.03 if st == "high_confidence" else 1.0,
        )
    elif st == "memory_fragmented":
        policy.update(
            max_system=min(4, DEFAULT_LAYER_LIMITS["system"] + 2),
            max_project=max(2, DEFAULT_LAYER_LIMITS["project"]),
            max_session=max(2, DEFAULT_LAYER_LIMITS["session"] - 2),
            diversity_level=0.4,
            contradiction_mode="off",
            compression_level="light",
            conflict_penalty_scale=1.12,
            confidence_scale=0.92,
            importance_floor_session=0.07,
            max_decay_session_keep=68.0,
        )

    # Ajustement léger si pression cognitive très haute (sans LLM)
    if pressure >= 78:
        policy["max_session"] = max(1, int(policy["max_session"]) - 1)
        policy["compression_level"] = "aggressive" if policy["compression_level"] == "none" else policy["compression_level"]
        policy["confidence_scale"] = round(float(policy["confidence_scale"]) * 0.96, 3)
    elif pressure >= 58:
        policy["diversity_level"] = round(min(0.95, float(policy["diversity_level"]) * 0.92), 3)

    policy["layer_limits"] = {
        "system": max(0, int(policy["max_system"])),
        "user": max(0, int(policy["max_user"])),
        "project": max(0, int(policy["max_project"])),
        "session": max(0, int(policy["max_session"])),
    }
    policy["explanation"] = explain_retrieval_policy(policy)
    return policy


def explain_retrieval_policy(policy: dict[str, Any]) -> str:
    """Résumé lisible opérateur (sanitisé)."""
    st = str(policy.get("state_resolved") or "")
    parts = [
        f"État={st}",
        f"couches max système/utilisateur/projet/session="
        f"{policy.get('max_system')}/{policy.get('max_user')}/{policy.get('max_project')}/{policy.get('max_session')}",
        f"diversité={policy.get('diversity_level')}",
        f"contradiction_mode={policy.get('contradiction_mode')}",
        f"compression={policy.get('compression_level')}",
        f"échelles conflit/confiance={policy.get('conflict_penalty_scale')}/{policy.get('confidence_scale')}",
    ]
    return sanitize_timeline_text(" | ".join(parts), 520)


def build_retrieval_policy(*, cognitive_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Construit la policy à partir du dernier snapshot cognitif (ou snapshot fourni)."""
    from app.cognition import cognitive_state_engine as cse

    snap = cognitive_snapshot if isinstance(cognitive_snapshot, dict) else cse.get_last_cognitive_state()
    state = str(snap.get("state") or "stable")
    pressure = float(snap.get("pressure_score") or 30.0)
    contra = str(snap.get("contradiction_level") or "low")
    base = policy_for_cognitive_state(state, pressure_score=pressure, contradiction_level=contra)
    out = {
        "status": "ok",
        "cognitive_state_source": state,
        "pressure_score_observed": pressure,
        **base,
    }
    set_last_retrieval_policy(out)
    return out


def merge_layer_caps(a: dict[str, int] | None, b: dict[str, int] | None) -> dict[str, int]:
    """Intersection stricte : le plus petit plafond par couche l’emporte."""
    keys = ("system", "user", "project", "session")
    out: dict[str, int] = {}
    da = dict(a or {})
    db = dict(b or {})
    for k in keys:
        va = int(da.get(k, DEFAULT_LAYER_LIMITS[k]))
        vb = int(db.get(k, DEFAULT_LAYER_LIMITS[k]))
        out[k] = max(0, min(va, vb))
    return out


def merge_scales(pa: float, pb: float, *, hi: float = 1.55, lo: float = 0.72) -> float:
    return round(max(lo, min(hi, float(pa) * float(pb))), 3)


def apply_retrieval_policy(
    entries: list[dict],
    query: str,
    *,
    policy: dict[str, Any],
    user_key: str = "",
    project_name_hint: str = "",
    is_guest: bool = True,
) -> list[dict]:
    """Wrapper explicite — délègue à ``gather_layered_candidates`` avec les bornes policy."""
    from app.memory.fractal_memory import gather_layered_candidates

    lims = policy.get("layer_limits") if isinstance(policy.get("layer_limits"), dict) else None
    return gather_layered_candidates(
        entries,
        query,
        user_key=user_key,
        project_name_hint=project_name_hint,
        is_guest=is_guest,
        layer_limits=lims,
        diversity_level=float(policy.get("diversity_level") or 0.5),
        contradiction_mode=str(policy.get("contradiction_mode") or "off"),
        compression_level=str(policy.get("compression_level") or "none"),
        importance_floor_session=float(policy.get("importance_floor_session") or 0.0),
        max_decay_session_keep=float(policy.get("max_decay_session_keep") or 100.0),
    )


def set_last_retrieval_policy(payload: dict[str, Any]) -> None:
    global _LAST_POLICY
    with _LAST_POLICY_LOCK:
        _LAST_POLICY = copy.deepcopy(payload)


def get_last_retrieval_policy() -> dict[str, Any]:
    with _LAST_POLICY_LOCK:
        return copy.deepcopy(_LAST_POLICY)


def lean_policy_response(policy: dict[str, Any]) -> dict[str, Any]:
    """Payload API sans champs internes lourds."""
    keys = (
        "status",
        "state_resolved",
        "cognitive_state_source",
        "pressure_score_observed",
        "max_system",
        "max_user",
        "max_project",
        "max_session",
        "diversity_level",
        "contradiction_mode",
        "compression_level",
        "conflict_penalty_scale",
        "confidence_scale",
        "explanation",
        "layer_limits",
    )
    return {k: policy[k] for k in keys if k in policy}


def clear_last_retrieval_policy_for_tests() -> None:
    with _LAST_POLICY_LOCK:
        _LAST_POLICY.clear()
        _LAST_POLICY["status"] = "empty"


def simulate_policy_for_state(state: str) -> dict[str, Any]:
    """Simulation sans lecture snapshot — utile pour debug / docs."""
    raw = (state or "stable").strip().lower()
    st = raw if raw in ALLOWED_STATES else "stable"
    base = policy_for_cognitive_state(st, pressure_score=42.0, contradiction_level="moderate")
    full = {
        "status": "ok",
        "simulate": True,
        "cognitive_state_source": st,
        "pressure_score_observed": None,
        **base,
    }
    lean = lean_policy_response(full)
    lean["simulate"] = True
    lean["state_requested"] = sanitize_timeline_text(raw, 80)
    return lean
