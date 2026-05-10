#!/usr/bin/env python3
"""Jeton owner OPENCHAWN_OWNER_TOKEN : bypass quota invité, sans fuite du secret dans JSON."""

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

OWNER_TOK = "oc_owner_test_token_v1162_do_not_commit_real"


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.settings import reload_settings

    os.environ["OPENCHAWN_OWNER_TOKEN"] = OWNER_TOK
    os.environ["GUEST_DAILY_MESSAGE_LIMIT"] = "3"
    reload_settings()

    def _fake_gen(**kwargs):
        return {
            "output": "mock reply",
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
    base_hdr = {"X-Guest-Session": sid}
    owner_hdr = {
        **base_hdr,
        "Authorization": f"Bearer {OWNER_TOK}",
    }
    bad_owner_hdr = {
        **base_hdr,
        "Authorization": "Bearer wrong-token-xxxxxxxxxxxx",
    }

    # --- Invité : 3 messages puis 429 ---
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        for i in range(3):
            time.sleep(2.1)
            r = client.post("/chat", json={"message": f"hi guest {i}"}, headers=base_hdr)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j.get("user_role") == "guest"
            assert j.get("owner_authenticated") is False
            assert "OPENCHAWN" not in json.dumps(j) and OWNER_TOK not in json.dumps(j)

        time.sleep(2.1)
        r429 = client.post("/chat", json={"message": "over quota"}, headers=base_hdr)
    assert r429.status_code == 429, r429.text

    # --- Mauvais Bearer : toujours invité, toujours bloqué ---
    time.sleep(2.1)
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        rw = client.post("/chat", json={"message": "bad owner token"}, headers=bad_owner_hdr)
    assert rw.status_code == 429, rw.text

    # --- Bon owner : bypass quota (session invité épuisée) ---
    time.sleep(2.1)
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        ro = client.post("/chat", json={"message": "owner hello EN"}, headers=owner_hdr)
    assert ro.status_code == 200, ro.text
    jo = ro.json()
    assert jo.get("owner_authenticated") is True
    assert jo.get("user_role") == "owner"
    assert jo.get("guest") is None
    dumped = json.dumps(jo)
    assert OWNER_TOK not in dumped and "Bearer" not in dumped

    time.sleep(2.1)
    with patch("app.api.chat.generate_response", side_effect=_fake_gen):
        ro2 = client.post(
            "/chat",
            params={"debug": "true"},
            json={"message": "owner bonjour FR"},
            headers=owner_hdr,
        )
    assert ro2.status_code == 200, ro2.text
    j2 = ro2.json()
    assert j2.get("owner_authenticated") is True and j2.get("user_role") == "owner"
    assert OWNER_TOK not in json.dumps(j2)
    assert "guest_limit" not in j2 and "guest_remaining" not in j2

    # Nettoyer ENV pour ne pas contaminer autres scripts du même process
    os.environ.pop("OPENCHAWN_OWNER_TOKEN", None)
    os.environ.pop("GUEST_DAILY_MESSAGE_LIMIT", None)
    reload_settings()

    print("OK test_owner_token_chat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
