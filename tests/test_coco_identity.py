"""COCO public identity — prompt assembly and UI contract."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_build_openchawn_base_system_prompt_contains_coco():
    from app.api.chat import build_openchawn_base_system_prompt

    prompt = build_openchawn_base_system_prompt()
    low = prompt.lower()
    assert "coco" in low
    assert "conversational openchawn core orchestrator" in low
    assert "powered by openchawn" in low
    assert "coco_public_identity_v12" in prompt


def test_assemble_chat_includes_coco_for_qui_es_tu():
    from app.api.chat import ChatRequest, assemble_chat_generation_inputs

    req = ChatRequest(message="Qui es-tu ?", profile="default")
    guest = {"is_guest": True, "guest_session_id": "test-coco", "ip": "127.0.0.1"}
    bundle = assemble_chat_generation_inputs(req, user=guest, persist_memory_side_effects=False)
    sp = bundle.get("system_prompt") or ""
    assert "COCO" in sp
    assert "Conversational OpenChawn Core Orchestrator" in sp
    assert bundle.get("detected_language") == "fr"


def test_static_index_html_coco_branding():
    from pathlib import Path

    html = Path(__file__).resolve().parents[1].joinpath("static", "index.html").read_text(encoding="utf-8")
    assert "<title>COCO</title>" in html
    assert '<div class="header-title">COCO</div>' in html
    assert "powered by OpenChawn" in html
    assert "coco-companion-presence" in html
    # Full expansion: discreet metadata anchor only (not visible header or hero copy)
    assert 'meta name="description"' in html
    assert "Conversational OpenChawn Core Orchestrator" in html
    assert "<p>COCO — Conversational OpenChawn Core Orchestrator" not in html


def test_chat_qui_es_tu_mocked_output_mentions_coco():
    from app.main import app

    def _fake_gen(**kwargs):
        assert "COCO" in (kwargs.get("system_prompt") or "")
        return {
            "output": (
                "Je suis COCO, Conversational OpenChawn Core Orchestrator, "
                "powered by OpenChawn."
            ),
            "success": True,
            "provider": "mock",
            "status_code": 200,
            "forced_french_runtime_removed": False,
            "prompt_contains_forced_french_before_sanitize": False,
        }

    client = TestClient(app)
    sg = client.post("/guest/session", json={})
    assert sg.status_code == 200
    hdr = {"X-Guest-Session": sg.json()["session_id"]}

    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        r = client.post("/chat", json={"message": "Qui es-tu ?"}, headers=hdr)
    assert r.status_code == 200, r.text
    out = (r.json().get("output") or "").lower()
    assert "coco" in out
    assert "conversational openchawn core orchestrator" in out
    assert "openchawn" in out
