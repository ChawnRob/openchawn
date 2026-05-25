"""COCO Second Brain chip — active control with AFFiNE open (no API sync yet)."""

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
    assert 'data-coco-action="open-affine-second-brain"' in line


def test_second_brain_active_cursor_styles():
    html = _html()
    assert ".coco-future-btn.coco-second-brain-btn" in html
    assert "cursor: pointer" in html


def test_second_brain_affine_open_handler():
    html = _html()
    assert "ocOpenAffineSecondBrain" in html
    assert "ocResolveAffineUrl" in html
    assert "ocBuildAffineDesktopDeepLink" in html
    assert "ocOpenExternalWebTab" in html
    assert "window.location.href = affineUrl" not in html
    assert "window.open(affineUrl" not in html
    assert "second-brain-bridge" not in html


def test_coco_identity_unchanged():
    html = _html()
    assert "<title>COCO</title>" in html
    assert 'class="header-title">COCO</div>' in html
    assert "powered by OpenChawn" in html
