#!/usr/bin/env python3
"""Vérifie le chemin langue du chat runtime (sans réseau, sans appel LLM)."""

from __future__ import annotations

import sys
import time
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
    assert (
        "apiFetch('/api/chat'" not in static
    ), "l'UI ne doit pas composer POST /api/chat (alias curl / integrations)."

    guest = {"is_guest": True, "guest_session_id": "rtest", "ip": "127.0.0.1"}
    assert resolve_profile_id(ChatRequest(message="hi"), guest) == "default"
    assert resolve_profile_id(ChatRequest(message="hi", profile="fluxorca"), guest) == "fluxorca"

    fp = get_profile("fluxorca").get("system_prompt", "")
    assert "fluxorca" in fp.lower()
    assert "english" in fp.lower()

    en_inst = build_language_instruction("Explain OpenChawn")
    assert "english" in en_inst.lower()
    fr_inst = build_language_instruction("Explique OpenChawn")
    assert "français" in fr_inst.lower()
    tr = build_language_instruction("Traduis ce texte en anglais : Bonjour")
    assert "translation" in tr.lower() and "english" in tr.lower()

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
    assert body.get("chat_routes_production") == ["POST /chat", "POST /api/chat"]
    assert body["profile_used"] == "fluxorca"
    assert body.get("detected_language") == "en"

    assert ChatRequest(message="ping", project="openchawn").project_name == "openchawn"

    from unittest.mock import patch

    hdr = {}
    sg = client.post("/guest/session", json={})
    assert sg.status_code == 200
    hdr["X-Guest-Session"] = sg.json()["session_id"]

    def _fake_gen(**kwargs):
        return {
            "output": "I am fine.",
            "success": True,
            "provider": "mock",
            "status_code": 200,
            "forced_french_runtime_removed": False,
            "prompt_contains_forced_french_before_sanitize": False,
        }

    payload = {"message": "hello how are you?", "project": "openchawn"}

    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        rb = client.post("/chat", params={"debug": "true"}, json=payload, headers=hdr)
        # Même garde 2s que la prod entre deux messages (IP + session guest).
        time.sleep(2.1)
        ra = client.post("/api/chat", params={"debug": "true"}, json=payload, headers=hdr)
    assert rb.status_code == 200, rb.text
    assert ra.status_code == 200, ra.text
    jb = rb.json()
    ja = ra.json()
    assert jb["route_used"] == "POST /chat"
    assert ja["route_used"] == "POST /api/chat"
    assert jb["handler_used"] == "handle_chat_request"
    assert ja["handler_used"] == jb["handler_used"]
    assert jb["response_language_mode"] == "auto"
    assert jb["detected_language"] == "en"
    assert jb["final_language"] == "en"
    assert jb.get("forced_french_runtime_detected") is False

    print("OK test_runtime_chat_language_path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
