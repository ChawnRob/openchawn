#!/usr/bin/env python3
"""
Blocage incident V11.6 : trajectoire langue + absence de formulations prototype forced-FR
dans l'assemblage prompt (sans appel LLM).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Comparables à _normalize_for_match (accent-stripped lower).
_FORBIDDEN_NORM_FRAGMENTS = (
    "je ne parle qu'en francais",
    "je communique uniquement en francais",
    "repondre uniquement en francais",
    "formule-la en francais",
)


def _corpus_normalized(bundle: dict) -> str:
    from app.core.runtime_language_guard import _normalize_for_match

    parts = [
        str(bundle.get("lang_instruction") or ""),
        str(bundle.get("sanitized_system_prompt") or ""),
        str(bundle.get("sanitized_user_message") or ""),
    ]
    return _normalize_for_match("\n".join(parts))


def assert_no_forbidden(corpus_nm: str, label: str) -> None:
    for frag in _FORBIDDEN_NORM_FRAGMENTS:
        assert frag not in corpus_nm, f"toxique forced-FR [{label}] contient motif: {frag!r}"


def main() -> int:
    from fastapi.testclient import TestClient

    from app.api.chat import ChatRequest, assemble_chat_generation_inputs
    from app.main import app

    stub = {
        "is_guest": True,
        "guest_session_id": "no-ff-runtime-test",
        "ip": "127.0.0.1",
    }

    scenarios: list[tuple[str, str, str]] = [
        (
            "hello how are you today?",
            "guest",
            "en",
        ),
        (
            "bonjour comment ça va ?",
            "guest",
            "fr",
        ),
        (
            "Translate this to English: bonjour",
            "guest",
            "en",
        ),
    ]

    client = TestClient(app)
    r_meta = client.get("/__runtime")
    assert r_meta.status_code == 200, r_meta.text
    jm = r_meta.json()
    assert jm.get("route_signature") == "GET___RUNTIME_INCIDENT_V116"
    assert jm.get("language_policy_version")

    for message, profile, want_final in scenarios:
        rr = client.post("/__debug/language-dry-run", json={"message": message, "profile": profile})
        assert rr.status_code == 200, rr.text
        dj = rr.json()
        assert dj["final_language"] == want_final, (message, dj)

        cr = ChatRequest(message=message, profile=profile or "")
        b = assemble_chat_generation_inputs(cr, user=stub, persist_memory_side_effects=False)
        assert b["final_language_hint"] == want_final, message

        corp = _corpus_normalized(b)
        assert_no_forbidden(corp, message[:48])

        assert not dj[
            "sanitized_still_contains_forced_french"
        ], f"sanitized still toxic: {message!r} -> {dj}"

    print("OK test_no_forced_french_runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
