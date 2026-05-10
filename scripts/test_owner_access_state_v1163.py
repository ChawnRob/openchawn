#!/usr/bin/env python3
"""V11.6.3 — Contrat réponses /chat utilisé par la barre sys (owner_authenticated, rôles, quota, aucune fuite)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OWNER_TOK = "oc_owner_v1163_gate_token_do_not_commit"


def assert_no_secret_leak(body: dict) -> None:
    dumped = json.dumps(body, ensure_ascii=False)
    forbidden = ("OPENCHAWN_OWNER_TOKEN", OWNER_TOK, "Bearer ")
    for needle in forbidden:
        assert needle not in dumped, f"Leak forbidden fragment in JSON: {needle!r}"


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.settings import reload_settings

    os.environ["OPENCHAWN_OWNER_TOKEN"] = OWNER_TOK
    os.environ.setdefault("GUEST_DAILY_MESSAGE_LIMIT", "5")
    reload_settings()

    def _fake_gen(**kwargs):
        return {
            "output": "mock reply v1163",
            "success": True,
            "provider": "mock",
            "status_code": 200,
            "forced_french_runtime_removed": False,
            "prompt_contains_forced_french_before_sanitize": False,
        }

    client = TestClient(app)
    sg = client.post("/guest/session", json={})
    assert sg.status_code == 200, sg.text
    sid = sg.json()["session_id"]

    hdr_guest = {"X-Guest-Session": sid}
    hdr_owner = {**hdr_guest, "Authorization": f"Bearer {OWNER_TOK}"}
    hdr_bad_owner = {**hdr_guest, "Authorization": "Bearer totally-wrong"}

    # --- Guest : owner_authenticated false, quota présente, pas guest si owner ---
    time.sleep(2.1)
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        r = client.post("/chat", json={"message": "hello gate guest"}, headers=hdr_guest)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("user_role") == "guest"
    assert j.get("owner_authenticated") is False
    assert j.get("guest") is True
    assert "quota_remaining" in j
    assert_no_secret_leak(j)

    # --- Owner validé : owner_authenticated true, pas consommation métier guest dans le JSON (pas de guest=True) ---
    time.sleep(2.1)
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        ro = client.post("/chat", json={"message": "owner ping"}, headers=hdr_owner)
    assert ro.status_code == 200, ro.text
    jo = ro.json()
    assert jo.get("user_role") == "owner"
    assert jo.get("owner_authenticated") is True
    assert jo.get("guest") is None
    assert "quota_remaining" not in jo
    assert_no_secret_leak(jo)

    # --- Bearer invalide : reste guest, pas owner_authenticated ---
    time.sleep(2.1)
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        rw = client.post("/chat", json={"message": "wrong bearer"}, headers=hdr_bad_owner)
    assert rw.status_code == 200, rw.text
    jw = rw.json()
    assert jw.get("user_role") == "guest"
    assert jw.get("owner_authenticated") is False
    assert_no_secret_leak(jw)

    os.environ.pop("OPENCHAWN_OWNER_TOKEN", None)
    reload_settings()

    print("OK test_owner_access_state_v1163")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
