"""
COCO File Intake — validate uploads and run in-memory analysis (V1).

Accepts multipart upload, validates type/size/signature/filename.
Image types: optional OpenAI vision analysis (no durable storage).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth.deps import get_current_user_or_guest
from app.files_intake.image_analysis import (
    IMAGE_MIME_TYPES,
    ImageAnalysisError,
    VisionUnavailableError,
    analyze_image_bytes,
)
from app.files_intake.session_image_context import (
    build_last_image_context,
    session_key_from_user,
    set_last_image_context,
)

logger = logging.getLogger("openchawn.files_intake")

router = APIRouter(tags=["openchawn-files"])

INTAKE_VERSION = "file_intake_v1"
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_CONTENT_TYPES: dict[str, tuple[str, ...]] = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/webp": (".webp",),
    "application/pdf": (".pdf",),
    "text/plain": (".txt",),
    "text/csv": (".csv",),
}

# Magic-byte prefixes required for binary types (spoof resistance).
_BINARY_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "application/pdf": (b"%PDF",),
}

# Reject text uploads that begin with known binary signatures.
_TEXT_FORBIDDEN_PREFIXES: tuple[bytes, ...] = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"MZ",
    b"%PDF",
    b"RIFF",
)

ANALYSIS_ENABLED = True
READY_MESSAGE = "Fichier reçu."
NON_IMAGE_MESSAGE = (
    "Fichier reçu. L'analyse automatique V1 concerne uniquement les images "
    "(PNG, JPEG, WebP)."
)


def _failure(
    failure_mode: str,
    message: str,
    status_code: int,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "ok": False,
            "failure_mode": failure_mode,
            "message": message,
            "analysis_enabled": ANALYSIS_ENABLED,
            "intake_version": INTAKE_VERSION,
        },
    )


def _normalize_content_type(raw: str | None) -> str:
    return (raw or "").split(";")[0].strip().lower()


def _extension_ok(filename: str, allowed_exts: tuple[str, ...]) -> bool:
    ext = Path(filename or "").suffix.lower()
    return ext in allowed_exts


def sanitize_intake_filename(raw: str) -> str:
    """
    Return a safe basename only. Reject path traversal and separator injection.
    """
    name = (raw or "").strip()
    if not name:
        raise _failure("upload_failed", "No file provided.", 400)
    if "\x00" in name or ".." in name or "/" in name or "\\" in name:
        raise _failure("upload_failed", "Invalid filename.", 400)
    base = Path(name).name
    if not base or base in {".", ".."}:
        raise _failure("upload_failed", "Invalid filename.", 400)
    return base


def _resolve_allowed_type(filename: str, content_type: str) -> str | None:
    if content_type in ALLOWED_CONTENT_TYPES:
        if _extension_ok(filename, ALLOWED_CONTENT_TYPES[content_type]):
            return content_type
        return None
    ext = Path(filename or "").suffix.lower()
    for mime, exts in ALLOWED_CONTENT_TYPES.items():
        if ext in exts:
            return mime
    return None


def _webp_valid(payload: bytes) -> bool:
    return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"


def validate_intake_payload(resolved_type: str, payload: bytes) -> None:
    """Verify magic bytes match declared type; reject disguised binaries."""
    if not payload:
        raise _failure("upload_failed", "Uploaded file is empty.", 400)

    if resolved_type == "image/webp":
        if not _webp_valid(payload):
            raise _failure(
                "unsupported_file_type",
                "File content does not match declared WebP format.",
                415,
            )
        return

    if resolved_type in _BINARY_SIGNATURES:
        prefixes = _BINARY_SIGNATURES[resolved_type]
        if not any(payload.startswith(prefix) for prefix in prefixes):
            raise _failure(
                "unsupported_file_type",
                "File content does not match declared file type.",
                415,
            )
        return

    if resolved_type in {"text/plain", "text/csv"}:
        for prefix in _TEXT_FORBIDDEN_PREFIXES:
            if payload.startswith(prefix):
                raise _failure(
                    "unsupported_file_type",
                    "Text file contains binary content signature.",
                    415,
                )


async def _read_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        block = await upload.read(65536)
        if not block:
            break
        total += len(block)
        if total > max_bytes:
            raise _failure(
                "file_too_large",
                f"File exceeds maximum size of {max_bytes // (1024 * 1024)} MB.",
                413,
            )
        chunks.append(block)
    return b"".join(chunks)


@router.post("/api/files/intake")
async def post_files_intake(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user_or_guest),
):
    """
    V1 file intake: validate and acknowledge upload without persisting or analyzing.

    Auth: same as POST /chat (guest session or Bearer).
    """

    if not file or not (file.filename or "").strip():
        raise _failure("upload_failed", "No file provided.", 400)

    filename = sanitize_intake_filename(file.filename or "")
    declared_type = _normalize_content_type(file.content_type)
    resolved_type = _resolve_allowed_type(filename, declared_type)

    if not resolved_type:
        raise _failure(
            "unsupported_file_type",
            "Unsupported file type. Allowed: PNG, JPEG, WebP, PDF, plain text, CSV.",
            415,
        )

    try:
        payload = await _read_bounded(file, MAX_FILE_BYTES)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("file intake read failed | error=%s", exc.__class__.__name__)
        raise _failure("upload_failed", "Could not read uploaded file.", 400) from exc

    validate_intake_payload(resolved_type, payload)

    logger.info(
        "file_intake_v1 ok | filename=%s | size=%s | type=%s | guest=%s",
        filename[:64],
        len(payload),
        resolved_type,
        bool(user.get("is_guest")),
    )

    if resolved_type in IMAGE_MIME_TYPES:
        try:
            analysis = analyze_image_bytes(
                payload=payload,
                content_type=resolved_type,
                filename=filename,
            )
        except VisionUnavailableError as exc:
            raise _failure("vision_unavailable", str(exc), 503) from exc
        except ImageAnalysisError as exc:
            raise _failure("analysis_failed", str(exc), 502) from exc

        analysis_payload = analysis.to_payload()
        image_ctx = build_last_image_context(
            filename=filename,
            mime_type=resolved_type,
            description=analysis.description,
            detected_elements=analysis.detected_elements,
        )
        set_last_image_context(session_key_from_user(user), image_ctx)

        return {
            "ok": True,
            "status": "analyzed",
            "message": analysis.to_message(),
            "filename": filename,
            "size_bytes": len(payload),
            "content_type": resolved_type,
            "analysis_enabled": True,
            "analysis": analysis_payload,
            "media_id": image_ctx.media_id,
            "last_image_context": image_ctx.to_dict(),
            "stored": False,
            "intake_version": INTAKE_VERSION,
            "failure_mode": None,
        }

    return {
        "ok": True,
        "status": "ready",
        "message": NON_IMAGE_MESSAGE,
        "filename": filename,
        "size_bytes": len(payload),
        "content_type": resolved_type,
        "analysis_enabled": False,
        "stored": False,
        "intake_version": INTAKE_VERSION,
        "failure_mode": None,
    }
