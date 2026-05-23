"""COCO Second Brain chip — active placeholder (no AFFiNE API yet)."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_second_brain_chip_not_disabled():
    html = _html()
    lines = [
        ln
        for ln in html.splitlines()
        if "coco-second-brain-btn" in ln and ">Second Brain</button>" in ln
    ]
    assert len(lines) == 1
    line = lines[0]
    assert "disabled" not in line
    assert 'aria-disabled="true"' not in line
    assert 'data-coco-action="second-brain-bridge"' in line


def test_second_brain_active_cursor_styles():
    html = _html()
    assert ".coco-future-btn.coco-second-brain-btn" in html
    assert "cursor: pointer" in html


def test_second_brain_placeholder_handler():
    html = _html()
    assert "Placeholder action for the future AFFiNE Second Brain bridge" in html
    assert "Second Brain bridge is ready for connection" in html
    assert "AFFiNE API integration is not connected yet" in html
    assert "ocHandleSecondBrainBridge" in html
    assert "addMsg('assistant', COCO_SECOND_BRAIN_PLACEHOLDER_MSG)" in html


def test_coco_identity_unchanged():
    html = _html()
    assert "<title>COCO</title>" in html
    assert 'class="header-title">COCO</div>' in html
    assert "powered by OpenChawn" in html
