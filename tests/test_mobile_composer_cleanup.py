"""Mobile composer cleanup — + menu, mic placement, crop auto-open, PR #14 flow."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_mobile_plus_button_opens_photo_gallery_file_menu():
    html = _html()
    assert 'class="oc-composer-plus-glyph"' in html
    assert ">+</span>" in html
    handler = html.split("function ocHandleAttachButtonClick")[1].split("function ocBindFileIntakeTap")[0]
    assert "ocOpenFileIntakeActionSheet()" in handler
    assert "Prendre une photo" in html
    assert "Photothèque" in html
    assert "Choisir un fichier" in html
    setup = html.split("(function ocFileIntakeUiSetup()")[1].split("})();")[0]
    assert "ocPickFileIntakeSource('camera')" in setup
    assert "ocPickFileIntakeSource('gallery')" in setup
    assert "ocPickFileIntakeSource('file')" in setup


def test_mic_hidden_from_main_composer_bar_on_mobile():
    html = _html()
    block = html.split("/* V11.6.3 mobile composer vertical alignment fix */")[1].split("@media (max-width: 896px)")[0]
    selector = "html.ux-chat-clean .clean-input-shell .input-wrapper .mic-btn"
    assert selector in block
    mic_rule = block.split(selector)[1].split("html.ux-chat-clean .clean-input-shell .input-wrapper > #btnImportPlus")[0]
    assert "display: none !important" in mic_rule


def test_mic_mounted_in_compact_toolbar_on_mobile():
    html = _html()
    assert 'id="cocoMobileMicMount"' in html
    assert 'id="ocComposerMobileToolbar"' in html
    idx = html.find('id="ocComposerMobileToolbar"')
    assert idx != -1
    toolbar_chunk = html[idx : idx + 900]
    assert "cocoMobileMicMount" in toolbar_chunk
    fn = html.split("function ocUpdateMobileComposerChrome")[1].split("function ocCloseMobileComposerMenu")[0]
    assert "micMount.appendChild(mic)" in fn


def test_second_brain_single_access_on_mobile():
    html = _html()
    assert "Open AFFiNE" in html
    assert "Open Second Brain" not in html
    block = html.split("/* V11.6.3 mobile composer vertical alignment fix */")[1].split("@media (max-width: 896px)")[0]
    assert "coco-future-controls" in block
    assert "display: none !important" in block.split(".coco-future-controls")[1][:80]
    assert "coco-prompt-chips .coco-prompt-chip:not(.coco-second-brain-btn)" in block
    assert "display: none !important" in block.split(":not(.coco-second-brain-btn)")[1][:80]


def test_mobile_composer_three_column_layout():
    html = _html()
    mobile = html.split("/* V11.6.3 mobile composer vertical alignment fix */")[1].split("@media (max-width: 896px)")[0]
    composer = mobile.split("/* Composer final: [ + ] [ champ texte large ] [ envoyer ] */")[1]
    assert "#btnFileIntake" in composer
    assert "textarea" in composer
    assert ".send-btn" in composer
    assert "flex: 1 1 auto" in composer.split("textarea {")[1]
    mic_rule = mobile.split("html.ux-chat-clean .clean-input-shell .input-wrapper .mic-btn")[1].split("#btnImportPlus")[0]
    assert "display: none !important" in mic_rule


def test_iphone_width_tightens_composer_controls():
    html = _html()
    iphone = html.split("@media (max-width: 430px)")[1].split("@media (max-width: 640px)")[0]
    assert "flex: 0 0 34px" in iphone
    assert "38px !important" in iphone


def test_message_field_keeps_width_on_mobile():
    html = _html()
    block = html.split("/* V11.6.3 mobile composer vertical alignment fix */")[1].split("@media (max-width: 896px)")[0]
    ta = block.split("html.ux-chat-clean .clean-input-shell .input-wrapper textarea {")[1].split("html.ux-chat-clean .msg {")[0]
    assert "flex: 1 1 auto" in ta
    assert "min-width: 0" in ta
    assert "width: 100%" in ta
    bar = block.split("html.ux-chat-clean .clean-input-shell .input-wrapper #btnFileIntake {")[1].split(".oc-composer-plus-glyph")[0]
    assert "flex: 0 0 36px" in bar


def test_crop_success_uses_center_square_crop():
    html = _html()
    attach_fn = html.split("async function ocAttachImageToComposer")[1].split("async function ocSendFileIntakeDraft")[0]
    assert "ocCropImageCenterSquare" in attach_fn
    assert "cropCenter" in attach_fn
    assert "mode: 'center_square'" in attach_fn
    confirm = html.split('id="btnFileIntakeCropConfirm"')[1][:120]
    assert "Valider" in confirm


def test_crop_failure_falls_back_to_original_image():
    html = _html()
    attach_fn = html.split("async function ocAttachImageToComposer")[1].split("async function ocSendFileIntakeDraft")[0]
    assert "crop_failed_fallback_original: true" in attach_fn
    assert "crop failed, using original image" in attach_fn
    catch_block = attach_fn.split("catch (err)")[1].split("ocRevokePendingImagePreviewUrl")[0]
    assert "return;" not in catch_block


def test_pr14_image_question_flow_intact():
    html = _html()
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "ocUploadPendingImageAttachment" in send_fn
    assert "chatBody.media_id" in send_fn
    assert "pendingImageAttachment" in html
    assert "ocAttachImageToComposer" in html
    attach_fn = html.split("async function ocAttachImageToComposer")[1].split("async function ocSendFileIntakeDraft")[0]
    assert "ocShowComposerAttachmentChip" in attach_fn
    assert "/api/files/intake" not in attach_fn


def test_auto_open_crop_after_mobile_image_selection():
    html = _html()
    assert "function ocShouldAutoOpenMobileImageCrop" in html
    preview_fn = html.split("function ocShowFileIntakePreview")[1].split("function ocLoadImageFromFile")[0]
    assert "ocShouldAutoOpenMobileImageCrop" in preview_fn
    assert "ocOpenFileIntakeCropModal()" in preview_fn
    crop_open = html.split("function ocOpenFileIntakeCropModal")[1].split("function ocRevokePendingImagePreviewUrl")[0]
    assert "ocScheduleFileIntakeCropperInit" in crop_open


def test_interactive_crop_supports_touch_and_pinch():
    html = _html()
    assert "/static/vendor/cropperjs/cropper.min.js" in html
    assert "function ocInitFileIntakeCropper" in html
    assert "function ocCropImageFromCropper" in html
    assert "getCroppedCanvas" in html
    assert "zoomOnTouch: true" in html
    assert "rotatable: true" in html
    assert 'id="btnCropReset"' in html
    assert 'id="btnCropRotate"' in html
    assert "ocCropperHasInstance" in html
    assert "cropInteractive: true" in html
    assert "Glissez l’image, pincez pour zoomer" in html


def test_image_pipeline_status_visible_during_send():
    html = _html()
    assert "function ocSetImagePipelineStatus" in html
    send_fn = html.split("async function send()")[1].split("var COCO_AFFINE_FALLBACK_URL")[0]
    assert "Image reçue…" in send_fn
    assert "Analyse visuelle en cours…" in send_fn
    assert "COCO prépare la réponse…" in send_fn
    assert "ocFriendlyVisionErrorMessage" in send_fn


def test_describe_previous_image_still_uses_last_image_context():
    from app.files_intake.session_image_context import message_references_recent_image

    assert message_references_recent_image("Peux-tu décrire l'image précédente ?")


def test_crop_does_not_upload_until_message_send():
    html = _html()
    confirm_handler = html.split("ocBindFileIntakeTap(btnCropConfirm")[1].split("ocBindFileIntakeTap(btnCropCancel")[0]
    assert "cropCenter: true" in confirm_handler
    assert "cropInteractive: true" in confirm_handler
    draft_fn = html.split("async function ocSendFileIntakeDraft")[1].split("function ocAcceptFileIntakeDraft")[0]
    assert "ocAttachImageToComposer" in draft_fn
    upload_fn = html.split("async function ocUploadPendingImageAttachment")[1].split("async function ocSubmitFileIntake")[0]
    assert "pendingImageAttachment" in upload_fn
    assert "ocUploadPendingImageAttachment" in html.split("async function send()")[1]
