"""COCO mobile file/photo intake — composer attach, preview, validate flow."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_mobile_attach_chip_in_toolbar():
    html = _html()
    assert 'id="btnFileIntake"' in html
    assert "oc-file-attach-btn" in html
    assert "coco-file-intake-chip" in html
    assert "📎 Photo/Fichier" in html
    assert 'id="cocoComposerAttachSlot"' in html
    assert 'id="btnMobileFileAttach"' not in html
    assert "oc-file-intake-desktop-only" not in html
    assert "oc-file-intake-mobile-only" not in html
    mobile_block = html.split("/* V11.6.3 mobile composer vertical alignment fix */")[1].split("@media (max-width: 896px)")[0]
    assert "html.ux-chat-clean .clean-input-shell .input-wrapper #btnFileIntake" in mobile_block
    assert "display: none !important" in mobile_block.split("input-wrapper #btnFileIntake")[1][:80]
    assert "html.ux-chat-clean .clean-input-shell .input-wrapper > #btnImportPlus" in mobile_block


def test_mobile_action_sheet_french_labels():
    html = _html()
    assert 'id="ocFileIntakeActionSheet"' in html
    assert "Prendre une photo" in html
    assert "Photothèque" in html
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
    assert "Recadrage avancé bientôt" in html
    assert "ocValidateFileIntakeDraft" in html
    assert "ocAcceptFileIntakeDraft" in html
    assert "btnFileIntakeValidate" in html
    assert "Valider" in html
    block = html.split("function ocValidateFileIntakeDraft")[1].split("function ocReplaceFileIntakeDraft")[0]
    assert "ocAttachImageToComposer" in block


def test_mobile_preview_has_send_and_crop_ctas():
    html = _html()
    assert 'id="ocFileIntakeMobilePreview"' in html
    assert 'id="btnFileIntakeCropSend"' in html
    assert "Recadrer" in html
    assert 'id="btnFileIntakeSendMobile"' in html
    assert "Joindre au message" in html
    assert 'id="btnFileIntakeRetake"' in html
    assert "Reprendre" in html
    assert 'id="btnFileIntakeDeleteMobile"' in html
    assert "Supprimer" in html
    assert "Recadrer bientôt" not in html
    assert "Photo sélectionnée" in html
    assert 'id="ocFileIntakeMobileFooter"' in html


def test_send_button_attaches_to_composer_not_isolated_upload():
    html = _html()
    setup = html.split("(function ocFileIntakeUiSetup()")[1].split("})();")[0]
    assert "ocSendFileIntakeDraft" in setup
    assert "ocBindFileIntakeTap(btnSend" in setup or "ocBindFileIntakeTap(btnSend," in setup
    assert "ocBindFileIntakeTap(btnSendMobile" in setup
    attach_fn = html.split("async function ocAttachImageToComposer")[1].split("async function ocSendFileIntakeDraft")[0]
    assert "pendingImageAttachment" in attach_fn
    assert "Photo reçue" not in attach_fn
    draft_fn = html.split("async function ocSendFileIntakeDraft")[1].split("function ocAcceptFileIntakeDraft")[0]
    assert "ocAttachImageToComposer" in draft_fn


def test_mobile_crop_modal_actions_exist():
    html = _html()
    assert 'id="ocFileIntakeCropModal"' in html
    assert 'id="btnFileIntakeCropConfirm"' in html
    assert 'id="btnFileIntakeCropCancel"' in html
    assert "Valider" in html.split('id="btnFileIntakeCropConfirm"')[1][:80]
    assert "Annuler" in html.split('id="btnFileIntakeCropCancel"')[1][:80]


def test_mobile_preview_uses_safe_area_padding():
    html = _html()
    block = html.split(".oc-fi-mobile-footer,")[1].split("html.is-mobile-file-intake-open")[0]
    assert "safe-area-inset-bottom" in block
    assert "calc(24px + env(safe-area-inset-bottom" in block


def test_mobile_footer_is_sticky_fixed_actions():
    html = _html()
    footer = html.split(".oc-fi-mobile-footer,")[1].split(".oc-file-intake-crop-actions .ux-tool-btn")[0]
    assert "position: sticky" in footer
    assert "bottom: 0" in footer


def test_mobile_send_without_crop_fallback_exists():
    html = _html()
    assert 'id="btnFileIntakeSendNoCrop"' in html
    assert "Joindre sans recadrer" in html
    assert 'id="btnFileIntakeCropSendDirect"' in html
    attach_fn = html.split("async function ocAttachImageToComposer")[1].split("async function ocSendFileIntakeDraft")[0]
    assert "crop failed, using original image" in attach_fn
    assert "crop_failed_fallback_original: true" in attach_fn


def test_mobile_actions_portaled_to_document_body():
    html = _html()
    portal = html.split("function ocPortalFileIntakeMobileNodes")[1].split("function ocSetMobileFileIntakeOpen")[0]
    assert "document.body.appendChild(preview)" in portal
    assert "document.body.appendChild(crop)" in portal


def test_mobile_actions_use_pointerup_and_click():
    html = _html()
    setup = html.split("function ocBindFileIntakeTap")[1].split("ocBindFileIntakeTap(btnAttach")[0]
    assert "addEventListener('click'" in setup
    assert "addEventListener('pointerup'" in setup


def test_mobile_preview_never_image_only_without_cta():
    html = _html()
    assert "Recadrer bientôt" not in html
    mobile = html.split('id="ocFileIntakeMobilePreview"')[1].split('id="ocFileIntakeCropModal"')[0]
    assert 'id="btnFileIntakeSendMobile"' in mobile
    assert "oc-fi-mobile-footer" in mobile
    assert "Photo sélectionnée" in mobile


def test_camera_capture_opens_mobile_preview():
    html = _html()
    assert "function ocShouldUseMobileFileIntakePreview" in html
    assert "source === 'camera'" in html
    accept = html.split("function ocAcceptFileIntakeDraft")[1].split("function ocClearFileIntakeDraft")[0]
    assert "ocShowFileIntakePreview(file, source)" in accept


def test_body_scroll_locked_while_mobile_intake_open():
    html = _html()
    assert "is-mobile-file-intake-open" in html
    assert "function ocSetMobileFileIntakeOpen" in html


def test_desktop_still_uses_direct_file_picker():
    html = _html()
    handler = html.split("function ocHandleAttachButtonClick")[1].split("function ocBindFileIntakeTap")[0]
    assert "ocPickFileIntakeSource('file')" in handler
    mobile_branch = handler.split("if (ocFileIntakeIsMobileComposer())")[1].split("return;")[0]
    assert "ocOpenFileIntakeActionSheet()" in mobile_branch
    assert "ocPickFileIntakeSource('file')" not in mobile_branch


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


def test_file_intake_attach_button_has_tap_binding():
    html = _html()
    setup = html.split("(function ocFileIntakeUiSetup()")[1].split("})();")[0]
    assert "ocBindFileIntakeTap(btnAttach" in setup
    assert "addEventListener('pointerup'" in setup
    assert "ocHandleAttachButtonClick" in setup


def test_mobile_plus_opens_action_sheet_not_direct_picker():
    html = _html()
    handler = html.split("function ocHandleAttachButtonClick")[1].split("function ocBindFileIntakeTap")[0]
    assert "if (ocFileIntakeIsMobileComposer())" in handler
    mobile_branch = handler.split("if (ocFileIntakeIsMobileComposer())")[1].split("ocPickFileIntakeSource('file')")[0]
    assert "ocOpenFileIntakeActionSheet()" in mobile_branch
    assert "oc-composer-plus-glyph" in html


def test_action_sheet_wires_expected_input_ids():
    html = _html()
    setup = html.split("(function ocFileIntakeUiSetup()")[1].split("})();")[0]
    assert "ocFileIntakePickCamera" in setup
    assert "ocPickFileIntakeSource('camera')" in setup
    assert "ocFileIntakePickGallery" in setup
    assert "ocPickFileIntakeSource('gallery')" in setup
    assert "ocFileIntakePickFile" in setup
    assert "ocPickFileIntakeSource('file')" in setup
    picker = html.split("function ocPickFileIntakeSource")[1].split("function ocWireFileIntakeInput")[0]
    assert "fileIntakeInputCamera" in picker
    assert "fileIntakeInputGallery" in picker
    assert "fileIntakeInputFile" in picker
    click_pos = picker.find("input.click()")
    close_pos = picker.find("ocCloseFileIntakeActionSheet()")
    assert click_pos != -1 and close_pos != -1 and click_pos < close_pos


def test_mobile_hud_does_not_use_display_contents():
    html = _html()
    assert "display:contents breaks position:fixed action sheets on iOS Safari" in html
    idx = html.find("html.ux-chat-clean .oc-mobile-composer-hud {")
    assert idx != -1
    hud_rule = html[idx : idx + 320]
    assert "display: block" in hud_rule
    assert "display: contents" not in hud_rule
    assert "pointer-events: none" in hud_rule


def test_file_intake_sheet_portaled_to_body_on_open():
    html = _html()
    assert "function ocPortalFileIntakeSheetNodes()" in html
    open_fn = html.split("function ocOpenFileIntakeActionSheet")[1].split("function ocCloseFileIntakeActionSheet")[0]
    assert "ocPortalFileIntakeSheetNodes()" in open_fn
    assert "document.body.appendChild" in html


def test_attach_button_not_desktop_only():
    """The attach chip lives in the toolbar row and stays hidden inside the input wrapper on mobile."""
    html = _html()
    attach_rule = html.split("#btnFileIntake,")[1].split("body.oc-night-mode #btnFileIntake")[0]
    assert "display: inline-flex" in attach_rule
    assert "oc-attach-btn" in html
    assert "coco-file-intake-chip" in html
    assert "📎 Photo/Fichier" in html
    assert 'id="cocoComposerAttachSlot"' in html
    mobile_rule = html.split(
        "html.ux-chat-clean .clean-input-shell .input-wrapper #btnFileIntake"
    )[1].split("}")[0]
    assert "display: none !important" in mobile_rule


def test_attach_button_night_mode_visible_styles():
    html = _html()
    assert "html.oc-theme-night #btnFileIntake" in html
    assert "body.oc-night-mode #btnFileIntake" in html
    assert '[data-theme="night"] #btnFileIntake' in html
    assert "rgba(3, 18, 31, 0.96)" in html
    assert "rgba(89, 226, 255, 0.7)" in html
    chip_rule = html.split("html.ux-chat-clean #btnFileIntake.coco-file-intake-chip {")[1].split(
        "html.ux-chat-clean #btnFileIntake.coco-file-intake-chip:hover"
    )[0]
    assert "border-radius: 999px" in chip_rule


def test_file_input_accepts_required_types():
    html = _html()
    file_input = html.split('id="fileIntakeInputFile"')[1].split(">")[0]
    for token in (".png", ".jpg", ".jpeg", ".webp", ".pdf", ".txt"):
        assert token in file_input
    for mime in ("image/png", "image/jpeg", "image/webp", "application/pdf", "text/plain"):
        assert mime in file_input


def test_file_received_feedback_and_intake_endpoint():
    html = _html()
    assert "/api/files/intake" in html
    upload = html.split("async function ocUploadPendingImageAttachment")[1].split("async function ocSubmitFileIntake")[0]
    assert "new FormData()" in upload
    assert "media_id" in upload
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocUploadPendingImageAttachment" in send_fn
    assert "chatBody.media_id" in send_fn


def test_intake_ui_displays_server_message_for_analysis():
    html = _html()
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocUploadPendingImageAttachment" in send_fn
    assert "d.output" in send_fn or "d.response" in send_fn
    assert "analysis pipeline is not enabled yet" not in html
