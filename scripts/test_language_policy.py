#!/usr/bin/env python3
"""Smoke tests language_policy (sans LLM).
   cd openchawn && .venv/bin/python scripts/test_language_policy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.core.language_policy import (
        build_language_instruction,
        detect_explicit_language_request,
        detect_user_language,
        normalize_language_code,
    )
    from app.main import app

    assert detect_user_language("Bonjour, comment allez-vous aujourd'hui ?") == "fr"
    assert "français" in build_language_instruction("Bonjour à tous.")

    assert detect_user_language("Hello, how are you today?") == "en"
    assert "anglais" in build_language_instruction("Hello there.")

    mixed_fr_dom = (
        "Bonjour merci beaucoup pour votre aide avec ce problème "
        "je vous écris depuis Paris pour vous dire bonjour."
    )
    assert detect_user_language(mixed_fr_dom) == "fr"
    assert "français" in build_language_instruction(mixed_fr_dom)

    mixed_en_dom = (
        "Hello thanks very much for your help with this issue "
        "I am writing from London to ask how this works please."
    )
    assert detect_user_language(mixed_en_dom) == "en"

    explicit = "Pourrait-on avoir une version courte ? answer in English please."
    assert detect_user_language(explicit) == "en"
    assert "anglais" in build_language_instruction(explicit)
    req = detect_explicit_language_request(explicit)
    assert req and req.get("kind") == "explicit_language" and req.get("language") == "en"

    tr_en = "Traduis ce texte en anglais : Bonjour"
    req = detect_explicit_language_request(tr_en)
    assert req and req.get("kind") == "translation_target" and req.get("language") == "en"
    assert "traduction" in build_language_instruction(tr_en).lower()
    assert "anglais" in build_language_instruction(tr_en)

    tr_fr = "Translate this to French: Hello"
    req = detect_explicit_language_request(tr_fr)
    assert req and req.get("kind") == "translation_target" and req.get("language") == "fr"
    assert "français" in build_language_instruction(tr_fr)

    ask_en = "Réponds en anglais : explique OpenChawn"
    req = detect_explicit_language_request(ask_en)
    assert req and req.get("kind") == "explicit_language" and req.get("language") == "en"
    assert "anglais" in build_language_instruction(ask_en)

    assert detect_user_language("Explique OpenChawn") == "fr"
    assert "français" in build_language_instruction("Explique OpenChawn")
    assert detect_user_language("Explain OpenChawn") == "en"
    assert "anglais" in build_language_instruction("Explain OpenChawn")

    assert detect_user_language("xyz abc 12345 !!!") == "fr"
    assert "français" in build_language_instruction("@@@")

    assert normalize_language_code("EN-us") == "en"
    assert normalize_language_code("FR") == "fr"
    assert normalize_language_code("anglais") == "en"
    assert normalize_language_code("???") == "fr"

    client = TestClient(app)
    r = client.get("/health/language")
    assert r.status_code == 200
    body = r.json()
    assert body.get("language_policy_enabled") is True
    assert body.get("fallback_language") == "fr"
    assert isinstance(body.get("rule"), str) and body["rule"]

    print("OK language_policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
