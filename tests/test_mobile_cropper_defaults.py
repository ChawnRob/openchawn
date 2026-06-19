"""Mobile Cropper.js defaults — full-image crop, no destructive validate-without-edit."""

from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_cropper_defaults_maximize_visible_image():
    html = _html()
    opts = html.split("function ocCropperOptions()")[1].split("function ocCropperMaximizeInitialCropBox")[0]
    assert "aspectRatio: NaN" in opts
    assert "autoCropArea: 1" in opts
    assert "viewMode: 1" in opts
    assert "cropBoxResizable: true" in opts
    assert "ocCropperMaximizeInitialCropBox(this)" in opts or "ocCropperFinalizeInitialCrop(cropper)" in opts
    assert "ocCropperSnapshotBaseline" in opts or "ocCropperFinalizeInitialCrop" in opts


def test_validate_without_edit_preserves_original_image():
    html = _html()
    export_fn = html.split("function ocCropImageFromCropper(file)")[1].split("function ocUpdateFileIntakeDraftFile")[0]
    assert "ocCropperIsEffectivelyUnchanged(ocCropperInstance)" in export_fn
    assert "ocCropperExportAreaRatio(ocCropperInstance) >= 0.9" in export_fn
    assert "return Promise.resolve(file)" in export_fn


def test_export_area_ratio_helper_exists():
    html = _html()
    fn = html.split("function ocCropperExportAreaRatio(cropper)")[1].split("function ocInitFileIntakeCropper")[0]
    assert "naturalWidth" in fn
    assert "naturalHeight" in fn
    assert "cw * ch" in fn or "(cw * ch)" in fn


def test_crop_reset_restores_full_image_box():
    html = _html()
    reset = html.split("function ocCropperReset()")[1].split("function ocShowFileIntakeError")[0]
    assert "ocCropperFinalizeInitialCrop(ocCropperInstance)" in reset


def test_regression_no_aggressive_square_auto_crop():
    """Échoue si le crop initial reste un carré réduit (82%)."""
    html = _html()
    opts = html.split("function ocCropperOptions()")[1].split("function ocCropperMaximizeInitialCropBox")[0]
    assert "autoCropArea: 0.82" not in opts
    assert "aspectRatio: 1" not in opts
    assert "cropBoxResizable: false" not in opts
