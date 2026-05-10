#!/usr/bin/env python3
"""V11.6.3 — Persona infra responsable multilingue : marqueur présent, aucune injection « français uniquement »."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.api.chat import ChatRequest, assemble_chat_generation_inputs, build_openchawn_base_system_prompt
    from app.core.runtime_language_guard import prompt_contains_forced_french
    from app.core.runtime_language_policy import (
        OPENCHAWN_ENVIRONMENTAL_IDENTITY_EN,
        OPENCHAWN_RUNTIME_LANGUAGE_POLICY_EN,
    )

    # Marqueurs audit / CI
    assert "marker_runtime_openchawn_environment_v1163" in OPENCHAWN_ENVIRONMENTAL_IDENTITY_EN
    assert "environmental_responsible_v1163" in OPENCHAWN_ENVIRONMENTAL_IDENTITY_EN

    base = build_openchawn_base_system_prompt()
    assert "marker_runtime_openchawn_environment_v1163" in base
    assert OPENCHAWN_RUNTIME_LANGUAGE_POLICY_EN in base
    assert not prompt_contains_forced_french(base), "base system must not trigger forced-french heuristics"

    # Anti greenwashing : consignes présentes (anglais prompt uniquement)
    low = base.lower()
    assert "when the infrastructure is ready" in low or "infrastructure is ready" in low
    assert "infomaniak" in low
    assert "100%" in base and "ecological" in low  # instruction « do not claim 100%… »

    stub_guest = {"is_guest": True, "guest_session_id": "guest_sess_test_v1163", "ip": "127.0.0.1"}
    cr = ChatRequest(message="Are you eco-friendly? Where is my data?")
    bundle = assemble_chat_generation_inputs(cr, user=stub_guest, persist_memory_side_effects=False)
    scan = (bundle["sanitized_system_prompt"] + "\n" + bundle["sanitized_user_message"]).strip()
    assert not prompt_contains_forced_french(scan), "assembled prompt must not trigger forced-french heuristics"
    assert bundle.get("system_core_contains_forced_french") is False
    assert "marker_runtime_openchawn_environment_v1163" in bundle["system_prompt"]

    # Chaînes interdites actives (ne doivent pas réapparaître comme consigne « positive » seule)
    for toxic in (
        "réponds uniquement en français",
        "reponds uniquement en francais",
        "français uniquement",
        "only french",
        "ne parle qu'en français",
    ):
        assert toxic.lower() not in _norm(base), f"unexpected legacy phrase in base prompt: {toxic!r}"

    print("OK test_persona_environmental_v1163")
    return 0


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


if __name__ == "__main__":
    raise SystemExit(main())
