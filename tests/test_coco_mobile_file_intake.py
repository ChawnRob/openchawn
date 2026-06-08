"""COCO mobile file/photo intake — composer attach, preview, validate flow."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_mobile_attach_button_visible_in_composer():
    html = _html()
    assert 'id="btnFileIntake"' in html
    assert "oc-file-attach-btn" in html
    assert 'id="btnMobileFileAttach"' not in html
    assert "oc-file-intake-desktop-only" not in html
    assert "oc-file-intake-mobile-only" not in html
    assert "html.ux-chat-clean .clean-input-shell .input-wrapper #btnFileIntake" in html
    assert "display: grid !important" in html
    assert "html.ux-chat-clean .clean-input-shell .input-wrapper > #btnImportPlus" in html


def test_mobile_action_sheet_french_labels():
    html = _html()
    assert 'id="ocFileIntakeActionSheet"' in html
    assert "Prendre une photo" in html
    assert "Choisir une photo" in html
    assert "Choisir un fichier" in html


def test_separate_intake_inputs():
    html = _html()
    assert 'id="fileIntakeInputCamera"' in html
    assert 'capture="environment"' in html
    assert 'id="fileIntakeInputGallery"' in html
    assert 'id="fileIntakeInputFile"' in html
    assert 'accept="image/*"' in html


def test_preview_validate_before_ready():
    html = _html()
    assert 'id="ocFileIntakePreview"' in html
    assert "Recadrer bientôt" in html
    assert "ocValidateFileIntakeDraft" in html
    assert "ocAcceptFileIntakeDraft" in html
    assert "btnFileIntakeValidate" in html
    assert "Valider" in html
    block = html.split("function ocValidateFileIntakeDraft")[1].split("function ocReplaceFileIntakeDraft")[0]
    assert "ocFileIntakePending" in block
    assert "ocShowFileIntakeBar" in block


def test_mobile_friendly_errors_and_formdata():
    html = _html()
    assert "ocShowFileIntakeError" in html
    assert "Fichier trop volumineux (max 10 Mo)" in html
    assert "Do not set Content-Type for FormData" in html
    api_fetch = html.split("async function apiFetch")[1].split("async function")[0]
    assert "delete headers['Content-Type']" in api_fetch


def test_attach_routes_mobile_action_sheet():
    html = _html()
    setup = html.split("(function ocFileIntakeUiSetup()")[1].split("})();")[0]
    assert "ocFileIntakeIsMobileComposer()" in setup
    assert "ocOpenFileIntakeActionSheet()" in setup
    assert "ocPickFileIntakeSource('file')" in setup


def test_attach_button_not_desktop_only():
    """The attach button is visible by default (desktop) and forced visible on mobile."""
    html = _html()
    base = html.split(".oc-file-attach-btn {")[1].split("}")[0]
    assert "display: grid" in base
    assert "display: none" not in base
    assert "width: 44px" in base
    assert 'aria-label="Joindre photo ou fichier"' in html
    mobile_rule = html.split(
        "html.ux-chat-clean .clean-input-shell .input-wrapper #btnFileIntake"
    )[1].split("}")[0]
    assert "display: grid !important" in mobile_rule


def test_file_input_accepts_required_types():
    html = _html()
    file_input = html.split('id="fileIntakeInputFile"')[1].split(">")[0]
    for token in (".png", ".jpg", ".jpeg", ".webp", ".pdf", ".txt"):
        assert token in file_input
    for mime in ("image/png", "image/jpeg", "image/webp", "application/pdf", "text/plain"):
        assert mime in file_input


def test_file_received_feedback_and_intake_endpoint():
    html = _html()
    assert "File received: " in html
    assert "/api/files/intake" in html
    submit = html.split("async function ocSubmitFileIntake")[1].split("\n}")[0]
    assert "new FormData()" in submit
    assert "Content-Type" not in submit
