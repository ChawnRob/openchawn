#!/usr/bin/env python3
"""Runtime language enforcement (policy + guard + detector) — sans LLM réel."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.core.language_policy import (
        build_language_instruction,
        detect_explicit_language_request,
        detect_user_language,
        normalize_language_code,
    )
    from app.core.runtime_language_guard import (
        assistant_reply_violates_english_user_expectation,
        prompt_contains_forced_french,
        sanitize_provider_prompts,
        skip_memory_entry_for_context_injection,
    )
    from app.lang.detector import LangResult, detect_language, get_language_name
    from app.main import app

    en_hello = "hello how are you and what's your name?"
    assert detect_user_language(en_hello) == "en"
    assert effective_final_language(en_hello) == "en"
    inst_en = build_language_instruction(en_hello)
    assert "english" in inst_en.lower()
    assert "français" not in inst_en.lower()

    fr_msg = "Bonjour, pourriez-vous m'expliquer ce projet en français simple ?"
    assert detect_user_language(fr_msg) == "fr"
    assert effective_final_language(fr_msg) == "fr"
    assert "français" in build_language_instruction(fr_msg).lower()

    tr = "Translate this to Spanish: Good morning"
    assert detect_explicit_language_request(tr) and detect_explicit_language_request(tr).get("language") == "es"
    assert "spanish" in build_language_instruction(tr).lower()

    assert normalize_language_code("not_a_real_lang_code_xyz") == "und"
    assert get_language_name("not_a_real_lang_code_xyz") == "not_a_real_lang_code_xyz"
    assert get_language_name("") == "unknown"

    assert normalize_language_code(None) == "und"

    toxic = {
        "metadata": {},
        "summary": "User prefers uniquement en français responses.",
        "user_message": "test",
        "assistant_response": "ok",
    }
    assert skip_memory_entry_for_context_injection(toxic)

    sp0 = "Rules: regles strictes de Robert.\nOK line."
    um0 = "Hello"
    sp1, um1, rm = sanitize_provider_prompts(sp0, um0)
    assert rm
    assert prompt_contains_forced_french(sp1 + um1) is False
    assert "Answer in the dominant language" in um1

    bad_reply = "Désolé, je ne peux m'exprimer qu'en français."
    assert assistant_reply_violates_english_user_expectation(bad_reply)
    assert not assistant_reply_violates_english_user_expectation("I am OpenChawn, here to help in English.")

    r_en = detect_language("hello how are you")
    assert isinstance(r_en, LangResult)
    assert r_en.lang == "en" and r_en.confidence >= 0.5

    # Chat: premier appel renvoie violation FR, second appel corrigé (mock)
    client = TestClient(app)
    gs = client.post("/guest/session", json={})
    assert gs.status_code == 200, gs.text
    sid = gs.json()["session_id"]
    hdr = {"X-Guest-Session": sid}

    seq = {"n": 0}

    def _fake_gen(*, system_prompt: str, user_message: str, provider_hint: str = ""):
        seq["n"] += 1
        if seq["n"] == 1:
            return {
                "output": "Désolé, je ne peux m'exprimer qu'en français.",
                "success": True,
                "provider": "mock",
                "status_code": 200,
                "forced_french_runtime_removed": False,
                "prompt_contains_forced_french_before_sanitize": False,
            }
        return {
            "output": "I'm doing well, thank you. I'm OpenChawn.",
            "success": True,
            "provider": "mock",
            "status_code": 200,
            "forced_french_runtime_removed": False,
            "prompt_contains_forced_french_before_sanitize": False,
        }

    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        r = client.post("/chat", json={"message": en_hello}, headers=hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "français" not in body.get("output", "").lower()
    assert "openchawn" in body.get("output", "").lower() or "well" in body.get("output", "").lower()

    print("OK test_runtime_language_enforcement")
    return 0


def effective_final_language(message: str) -> str:
    from app.core.language_policy import (
        detect_explicit_language_request,
        detect_user_language,
        normalize_language_code,
    )

    req = detect_explicit_language_request(message)
    if req:
        return normalize_language_code(req.get("language"))
    return detect_user_language(message)


if __name__ == "__main__":
    raise SystemExit(main())
