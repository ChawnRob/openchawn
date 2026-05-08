#!/usr/bin/env python3
"""Initial rules forced-french override tests."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.core import initial_rules as ir
    from app.core.language_policy import build_language_instruction
    from app.main import app

    tmp = Path(tempfile.mkdtemp(prefix="openchawn_rules_"))
    rules = tmp / "initial_rules.json"
    rules.write_text(
        '{"rules":["Répondre uniquement en français.","Toujours répondre en français.","Identity is OpenChawn."]}',
        encoding="utf-8",
    )
    os.environ["INITIAL_RULES_PATH"] = str(rules)

    rep = ir.load_initial_rules()
    assert rep.get("forced_french_rule_found") is True, rep
    assert rep.get("forced_french_rule_removed") is True, rep
    san = str(rep.get("sanitized_text") or "").lower()
    assert "uniquement en français" not in san
    assert "toujours répondre en français" not in san
    assert "language policy:" in san

    # language policy behavior
    assert "english" in build_language_instruction("Explain OpenChawn").lower()
    assert "français" in build_language_instruction("Explique OpenChawn")
    tr = build_language_instruction("Traduis ce texte en anglais : Bonjour")
    assert "translation" in tr.lower() and "english" in tr.lower()

    # /api/chat uses policy and does not inject forced french
    client = TestClient(app)
    gs = client.post("/guest/session")
    assert gs.status_code == 200
    sid = gs.json().get("session_id")
    captured = {}

    def _fake_generate_response(*, system_prompt: str, user_message: str, provider_hint: str = ""):
        captured["system_prompt"] = system_prompt
        captured["user_message"] = user_message
        return {"output": "ok", "success": True, "provider": "mock", "status_code": 200}

    with patch("app.api.chat.generate_response", side_effect=_fake_generate_response):
        en = client.post("/chat", json={"message": "Explain OpenChawn in one sentence"}, headers={"X-Guest-Session": sid})
        assert en.status_code == 200, en.text
        up = str(captured.get("user_message") or "").lower()
        sp = str(captured.get("system_prompt") or "").lower()
        assert "output language: english" in up or "english" in up
        assert "uniquement en français" not in up
        assert "toujours répondre en français" not in sp

    # health endpoint exposes audit
    h = client.get("/health/language")
    assert h.status_code == 200, h.text
    hb = h.json()
    assert hb.get("language_policy_enabled") is True
    assert hb.get("forced_french_rule_found") is True
    assert "translation_target" in (hb.get("priority") or [])

    print("OK initial_rules_language_override tmp=", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

