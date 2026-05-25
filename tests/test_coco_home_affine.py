"""COCO home screen + AFFiNE Second Brain UI contract."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_home_no_repeated_landing_paragraph_under_face():
    html = _html()
    assert "coco-companion-presence" in html
    assert "<p>COCO — Conversational OpenChawn Core Orchestrator" not in html
    assert "<p>COCO — Conversational OpenChawn Core Orchestrator. Powered by OpenChawn.</p>" not in html


def test_header_coco_and_powered_by_openchawn():
    html = _html()
    assert "<title>COCO</title>" in html
    assert 'class="header-title">COCO</div>' in html
    assert "powered by OpenChawn" in html


def test_ready_state_label_preserved():
    html = _html()
    assert 'class="coco-state-label"' in html
    assert "Ready</span>" in html or ">Ready</span>" in html


def test_second_brain_buttons_exist():
    html = _html()
    assert "coco-second-brain-btn" in html
    assert 'data-coco-action="open-affine-second-brain"' in html
    assert "Open Second Brain" in html
    assert ">Second Brain</button>" in html


def test_affine_url_resolution_and_fallback():
    html = _html()
    assert "function ocResolveAffineUrl" in html
    assert "OPENCHAWN_AFFINE_LOCAL_URL" in html
    assert "OPENCHAWN_AFFINE_URL" in html
    assert "data-affine-url" in html
    assert "https://app.affine.pro" in html
    assert "function ocOpenExternalWebTab" in html
    assert "window.location.href = affineUrl" not in html


def test_second_brain_microcopy_safe():
    html = _html()
    assert "AFFiNE opened in a separate tab/window" in html
    assert "AFFiNE is connected" not in html
    assert "OpenChawn stores your documents" not in html
    assert "Memory sync is active" not in html


def test_second_brain_aria_and_title():
    html = _html()
    assert html.count('title="Open AFFiNE Second Brain"') >= 2
    assert html.count('aria-label="Open AFFiNE Second Brain"') >= 2


def test_affine_handler_todo_comment():
    html = _html()
    assert "Future AFFiNE bridge must support local-first user ownership" in html
