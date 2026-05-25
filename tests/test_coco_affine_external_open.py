"""COCO AFFiNE external-open strategy — no in-tab navigation, safe deep links."""

from __future__ import annotations

import re
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _handler_block(html: str) -> str:
    start = html.index("function ocOpenAffineSecondBrain")
    end = html.index("document.addEventListener('click'", start)
    return html[start:end]


def test_coco_tab_never_navigated_away():
    block = _handler_block(_html())
    assert "window.location.href" not in block
    assert "location.assign" not in block
    assert "location.replace" not in block


def test_web_fallback_uses_external_target():
    html = _html()
    assert "function ocOpenExternalWebTab" in html
    assert "target: '_blank'" in html or "a.target = '_blank'" in html
    assert "noopener noreferrer" in html
    assert "function ocTriggerExternalOpen" in html


def test_toast_fallback_link_clickable_and_external():
    html = _html()
    assert "function ocShowCocoSecondBrainToast" in html
    assert "link.target = '_blank'" in html
    assert "link.rel = 'noopener noreferrer'" in html


def test_official_affine_desktop_deep_link_builder():
    html = _html()
    assert "function ocBuildAffineDesktopDeepLink" in html
    assert "COCO_AFFINE_DESKTOP_SCHEME = 'affine'" in html
    assert "params.set('new-tab', '1')" in html
    assert "COCO_AFFINE_DESKTOP_SCHEME +" in html


def test_no_browser_specific_forced_open():
    html = _html().lower()
    for needle in (
        "navigator.useragent",
        "safari",
        "chrome://",
        "ms-windows-store",
        "intent://",
    ):
        idx = html.find("ocopenaffinesecondbrain")
        affine_region = html[idx : idx + 8000] if idx >= 0 else ""
        assert needle not in affine_region, f"unexpected browser hack: {needle}"


def test_resolve_rejects_raw_affine_scheme_for_web():
    html = _html()
    assert "if (/^affine(-[a-z]+)?:\\/\\//i.test(resolved))" in html
    assert "return COCO_AFFINE_FALLBACK_URL" in html


def test_web_only_toast_explains_browser_choice():
    html = _html()
    assert (
        "AFFiNE opened in a separate tab/window. Browser choice is controlled by your system."
        in html
    )


def test_desktop_attempt_toast_with_web_fallback_link():
    html = _html()
    assert "Opening AFFiNE desktop if installed" in html
    assert "Otherwise open the web workspace:" in html
