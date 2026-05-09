#!/usr/bin/env python3
"""
Règles prototype « français obligatoire » : détection, filtrage runtime, politique unique.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _norm(t: str) -> str:
    from app.core.runtime_language_guard import _normalize_for_match

    return _normalize_for_match(t)


def main() -> int:
    from app.api.chat import SHARED_CHAT_HANDLER, route_post_api_chat, route_post_chat
    from app.config import LANG_INSTRUCTION
    from app.core.language_policy import derive_response_language_trace
    from app.core.runtime_language_guard import prompt_contains_forced_french, sanitize_provider_prompts
    from app.core.runtime_language_policy import OPENCHAWN_RUNTIME_LANGUAGE_POLICY_EN

    legacy_samples = [
        "Tu parles en français.",
        "Réponds en français clair.",
        "Réponds UNIQUEMENT en français.",
        "Réponds en français, avec précision, calme et structure.",
        "Ne mélange JAMAIS les langues.",
        "Je ne parle qu'en français, comme mes règles l'exigent.",
        "formule-la en français s'il te plaît.",
    ]
    for s in legacy_samples:
        assert prompt_contains_forced_french(s), f"attendu forced-french legacy pour: {s!r}"

    poisoned = (
        "Role meta.\n"
        "Réponds en français, avec précision, calme et structure.\n"
        "Tu parles en français.\n"
        "END."
    )
    sp_out, um_out, did = sanitize_provider_prompts(
        "system header\n" + legacy_samples[0],
        poisoned,
    )
    assert did is True
    blob = _norm(sp_out + "\n" + um_out)
    for toxic in (
        "tu parles en francais",
        "reponds en francais, avec precision, calme et structure",
        "reponds uniquement en francais",
        "ne melange jamais les langues",
        "francais clair",
    ):
        assert toxic not in blob, f"résidu toxique dans prompt sanitized: {toxic!r}"

    assert LANG_INSTRUCTION == OPENCHAWN_RUNTIME_LANGUAGE_POLICY_EN
    assert "Never force French by default" in OPENCHAWN_RUNTIME_LANGUAGE_POLICY_EN

    assert derive_response_language_trace("hello how are you and what's your name?")["final_language"] == "en"
    assert derive_response_language_trace("Bonjour, comment allez-vous ?")["final_language"] == "fr"
    tr = derive_response_language_trace("Traduis bonjour en espagnol")
    assert tr["response_language_mode"] == "translate"
    assert tr["final_language"] == "es"

    assert SHARED_CHAT_HANDLER.__name__ == "handle_chat_request"
    rc = inspect.getsource(route_post_chat)
    ra = inspect.getsource(route_post_api_chat)
    assert "handle_chat_request(" in rc and "handle_chat_request(" in ra

    print("OK test_legacy_french_prompt_neutralization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
