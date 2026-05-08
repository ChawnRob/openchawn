#!/usr/bin/env python3
"""Vérifie le chemin langue du chat runtime (sans réseau, sans appel LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.api.chat import ChatRequest, assemble_chat_generation_inputs, resolve_profile_id
    from app.core.language_policy import build_language_instruction
    from app.core.runtime_language_guard import prompt_contains_forced_french
    from app.main import app
    from app.memory.fractal_memory import MEMORY_LIFECYCLE_ARCHIVED, _deprecate_forced_french_runtime_memories
    from app.profiles import get_profile

    static = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "apiFetch('/chat'" in static, "frontend doit appeler POST /chat"
    assert "fetch(API + '/chat'" not in static  # legacy double prefix check
    assert "/api/chat" not in static or static.count("/api/chat") == 0

    guest = {"is_guest": True, "guest_session_id": "rtest", "ip": "127.0.0.1"}
    assert resolve_profile_id(ChatRequest(message="hi"), guest) == "default"
    assert resolve_profile_id(ChatRequest(message="hi", profile="fluxorca"), guest) == "fluxorca"

    fp = get_profile("fluxorca").get("system_prompt", "")
    assert "langue dominante" in fp.lower()
    assert "impos" in fp.lower()

    en_inst = build_language_instruction("Explain OpenChawn")
    assert "anglais" in en_inst.lower()
    fr_inst = build_language_instruction("Explique OpenChawn")
    assert "français" in fr_inst.lower()
    tr = build_language_instruction("Traduis ce texte en anglais : Bonjour")
    assert "traduction" in tr.lower() and "anglais" in tr.lower()

    bundle = assemble_chat_generation_inputs(
        ChatRequest(message="hello how are you and what's your name?", profile="fluxorca"),
        user=guest,
        persist_memory_side_effects=False,
    )
    scan = bundle["sanitized_system_prompt"] + "\n" + bundle["sanitized_user_message"]
    assert not prompt_contains_forced_french(scan), scan[:200]

    toxin = [
        {
            "metadata": {},
            "summary": "User set preference: parle uniquement en français.",
            "user_message": "",
            "assistant_response": "",
        }
    ]
    n = _deprecate_forced_french_runtime_memories(toxin)
    assert n == 1
    assert toxin[0]["lifecycle_status"] == MEMORY_LIFECYCLE_ARCHIVED
    assert toxin[0]["metadata"].get("forced_french_runtime_rule_removed") is True

    client = TestClient(app)
    r = client.post(
        "/health/language/chat-dry-run",
        json={"message": "hello how are you and what's your name?", "profile": "fluxorca"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route_used"] == "POST /chat"
    assert body["profile_used"] == "fluxorca"
    assert body.get("detected_language") == "en"

    print("OK test_runtime_chat_language_path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
