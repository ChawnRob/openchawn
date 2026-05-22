#!/usr/bin/env python3
"""Smoke: COCO identity in static/index.html + optional live « Qui es-tu ? »."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://www.openchawn.com"


def check_static_file() -> tuple[bool, str]:
    text = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    for needle in (
        "<title>COCO</title>",
        "powered by OpenChawn",
        "Conversational OpenChawn Core Orchestrator",
        "coco-companion-presence",
    ):
        if needle not in text:
            return False, f"missing in static/index.html: {needle!r}"
    return True, "static/index.html COCO branding OK"


def check_deployed_html(base_url: str, timeout: float) -> tuple[bool, str]:
    r = requests.get(base_url.rstrip("/") + "/", timeout=timeout)
    if r.status_code != 200:
        return False, f"GET / => HTTP {r.status_code}"
    body = r.text
    if "<title>COCO</title>" in body:
        return True, "deployed HTML has COCO title"
    m = re.search(r"<title>([^<]+)</title>", body, re.I)
    return False, f"deployed title={m.group(1) if m else '?'} (pre-COCO build likely)"


def check_live_qui_es_tu(base_url: str, timeout: float) -> tuple[bool, str]:
    s = requests.Session()
    gs = s.post(base_url.rstrip("/") + "/guest/session", json={}, timeout=timeout)
    if gs.status_code != 200:
        return False, f"guest/session => {gs.status_code}"
    sid = gs.json().get("session_id")
    ch = s.post(
        base_url.rstrip("/") + "/chat",
        json={"message": "Qui es-tu ?"},
        headers={"X-Guest-Session": sid},
        timeout=max(timeout, 90.0),
    )
    if ch.status_code != 200:
        return False, f"/chat => {ch.status_code}"
    out = (ch.json().get("output") or "").strip()
    low = out.lower()
    if "coco" not in low or "openchawn" not in low:
        return False, f"output missing COCO/OpenChawn: {out[:240]}"
    if not ("conversational" in low and "orchestrator" in low):
        return False, f"output missing acronym expansion: {out[:240]}"
    return True, f"live OK: {out[:100]}..."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--local-only", action="store_true")
    ap.add_argument("--skip-live-chat", action="store_true")
    args = ap.parse_args()

    ok = True
    good, msg = check_static_file()
    print(f"[{'PASS' if good else 'FAIL'}] static_file: {msg}")
    ok = ok and good

    if not args.local_only:
        good, msg = check_deployed_html(args.base_url, args.timeout)
        print(f"[{'PASS' if good else 'FAIL'}] deployed_html: {msg}")
        ok = ok and good
        if not args.skip_live_chat:
            good, msg = check_live_qui_es_tu(args.base_url, args.timeout)
            print(f"[{'PASS' if good else 'FAIL'}] live_qui_es_tu: {msg}")
            ok = ok and good

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
