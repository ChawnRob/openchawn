#!/usr/bin/env python3
"""Contrat routes chat V11.6 : langues, même handler /chat=/api/chat, outputs interdits."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.api.chat import SHARED_CHAT_HANDLER, handle_chat_request, route_post_api_chat, route_post_chat
    from app.core.language_policy import derive_response_language_trace, detect_surface_language
    from app.core.runtime_language_guard import RESPONSE_FORCED_FRENCH_SUBSTRINGS, _normalize_for_match
    from app.main import app

    tr_en = derive_response_language_trace("hello how are you and what's your name?")
    assert tr_en["response_language_mode"] == "auto"
    assert tr_en["final_language"] == "en"

    assert detect_surface_language("Bonjour, comment allez-vous aujourd'hui ?") == "fr"
    tr_fr = derive_response_language_trace("Bonjour, comment allez-vous aujourd'hui ?")
    assert tr_fr["response_language_mode"] == "auto"
    assert tr_fr["final_language"] == "fr"

    tr_es = derive_response_language_trace("Traduis « bonjour » en espagnol")
    assert tr_es["response_language_mode"] == "translate"
    assert tr_es["final_language"] == "es"

    assert SHARED_CHAT_HANDLER is handle_chat_request
    assert route_post_chat is not route_post_api_chat

    def forbidden_in_output(txt: str) -> bool:
        n = _normalize_for_match(txt)
        return any(p in n for p in RESPONSE_FORCED_FRENCH_SUBSTRINGS)

    def _fake_gen(**kwargs):
        return {
            "output": "I am OpenChawn, glad to help in English.",
            "success": True,
            "provider": "mock",
            "status_code": 200,
            "forced_french_runtime_removed": False,
            "prompt_contains_forced_french_before_sanitize": False,
        }

    client = TestClient(app)
    sg = client.post("/guest/session", json={})
    assert sg.status_code == 200, sg.text
    hdr = {"X-Guest-Session": sg.json()["session_id"]}
    qp = {"debug": "true"}

    en_body = {"message": "hello how are you?", "project": "openchawn"}

    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        rb = client.post("/chat", params=qp, json=en_body, headers=hdr)
        time.sleep(2.1)
        ra = client.post("/api/chat", params=qp, json=en_body, headers=hdr)
    assert rb.status_code == 200, rb.text
    assert ra.status_code == 200, ra.text
    jb, ja = rb.json(), ra.json()
    assert jb["handler_used"] == ja["handler_used"] == "handle_chat_request"
    assert jb["final_language"] == "en"
    assert ja["final_language"] == "en"
    assert jb["detected_language"] == "en"
    assert not forbidden_in_output(str(jb.get("output") or ""))

    time.sleep(2.1)
    excuse_calls: list[int] = []

    def _excuse_then_ok(**kwargs):
        excuse_calls.append(1)
        if len(excuse_calls) == 1:
            return {
                "output": "Désolé, je ne peux m'exprimer qu'en français.",
                "success": True,
                "provider": "mock",
                "status_code": 200,
                "forced_french_runtime_removed": False,
                "prompt_contains_forced_french_before_sanitize": False,
            }
        return _fake_gen(**kwargs)

    with patch("app.api.chat.generate_response", side_effect=_excuse_then_ok):
        rev = client.post(
            "/chat",
            json={"message": "hello how are you and what's your name?"},
            headers=hdr,
        )
    assert rev.status_code == 200, rev.text
    assert len(excuse_calls) == 2
    assert not forbidden_in_output(str(rev.json().get("output") or ""))

    time.sleep(2.1)
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        rfr = client.post(
            "/chat",
            params=qp,
            json={"message": "Bonjour, pouvez-vous m'aider pour un problème simple ?", "project": "openchawn"},
            headers=hdr,
        )
    assert rfr.status_code == 200, rfr.text
    bf = rfr.json()
    assert bf["final_language"] == "fr"

    assert not forbidden_in_output(str(bf.get("output") or ""))

    time.sleep(2.1)
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        rtr = client.post(
            "/chat",
            params=qp,
            json={"message": "Traduis « merci » en espagnol", "project": "openchawn"},
            headers=hdr,
        )
    assert rtr.status_code == 200, rtr.text
    bt = rtr.json()
    assert bt["response_language_mode"] == "translate"
    assert bt["final_language"] == "es"

    print("OK test_chat_route_contract_v116")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
