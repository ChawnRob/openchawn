"""COCO file intake V1 — validation, spoof resistance, no disk persistence."""

from __future__ import annotations

import io
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import guest as guest_auth
from app.files_intake.image_analysis import ImageAnalysisResult
from app.main import app
from app.memory.fractal_memory import MemoryWriteResult

_MOCK_IMAGE_ANALYSIS = ImageAnalysisResult(
    description="Image de test.",
    detected_elements=["élément test"],
    clarification_question=None,
    provider="openai",
    model="gpt-4o-mini",
    raw_text="{}",
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff\xe0"


def _reset_rate_limit_state() -> None:
    """Clear in-process middleware counters (shared TestClient IP hits /guest/session limit)."""
    from app import middleware as mw

    mw._buckets.clear()
    mw._last_chat_request_at.clear()
    mw._request_counts.clear()


def _reset_guest() -> None:
    guest_auth._sessions.clear()
    guest_auth._ip_sessions.clear()
    _reset_rate_limit_state()


def _guest_headers(client: TestClient) -> dict[str, str]:
    r = client.post("/guest/session")
    assert r.status_code == 200
    return {"X-Guest-Session": r.json()["session_id"]}


def _post_intake(client: TestClient, headers: dict[str, str], name: str, data: bytes, mime: str):
    files = {"file": (name, io.BytesIO(data), mime)}
    return client.post("/api/files/intake", files=files, headers=headers)


# 1. reject oversized file > 10 MB
def test_reject_oversized_file_over_10mb():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    big = b"x" * (10 * 1024 * 1024 + 1)
    r = _post_intake(client, headers, "big.txt", big, "text/plain")
    assert r.status_code == 413
    assert r.json()["detail"]["failure_mode"] == "file_too_large"


# 2. reject .exe renamed as .png
def test_reject_exe_renamed_as_png():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    r = _post_intake(client, headers, "fake.png", b"MZ\x90\x00" + b"\x00" * 32, "image/png")
    assert r.status_code == 415
    assert r.json()["detail"]["failure_mode"] == "unsupported_file_type"


# 3. reject image/png MIME with invalid magic bytes
def test_reject_png_mime_invalid_magic_bytes():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    r = _post_intake(client, headers, "bad.png", b"NOT_A_PNG_HEADER", "image/png")
    assert r.status_code == 415
    assert r.json()["detail"]["failure_mode"] == "unsupported_file_type"


# 4. reject path traversal filename
def test_reject_path_traversal_filename():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    r = _post_intake(client, headers, "../../secret.txt", b"hello", "text/plain")
    assert r.status_code == 400
    assert r.json()["detail"]["failure_mode"] == "upload_failed"


# 5. reject empty file
def test_reject_empty_file():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    r = _post_intake(client, headers, "empty.txt", b"", "text/plain")
    assert r.status_code == 400
    assert r.json()["detail"]["failure_mode"] == "upload_failed"


# 6. accept valid png magic bytes
def test_accept_valid_png_magic_bytes():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    data = PNG_MAGIC + b"\x00" * 64
    with patch(
        "app.api.files_intake.analyze_image_bytes",
        return_value=_MOCK_IMAGE_ANALYSIS,
    ):
        r = _post_intake(client, headers, "shot.png", data, "image/png")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["stored"] is False
    assert body["filename"] == "shot.png"
    assert body["content_type"] == "image/png"
    assert body["analysis_enabled"] is True


# 7. accept valid jpg magic bytes
def test_accept_valid_jpg_magic_bytes():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    data = JPEG_MAGIC + b"\x00" * 64
    with patch(
        "app.api.files_intake.analyze_image_bytes",
        return_value=_MOCK_IMAGE_ANALYSIS,
    ):
        r = _post_intake(client, headers, "photo.jpg", data, "image/jpeg")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content_type"] == "image/jpeg"
    assert body["stored"] is False
    assert body["analysis_enabled"] is True


# 8. accept valid txt under size limit
def test_accept_valid_txt_under_size_limit():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    content = b"hello intake"
    r = _post_intake(client, headers, "note.txt", content, "text/plain")
    assert r.status_code == 200
    assert r.json()["size_bytes"] == len(content)


# 9. verify file is not persisted to disk
def test_intake_does_not_persist_file_to_disk():
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)
    data = PNG_MAGIC + b"\x00" * 16

    with patch(
        "app.api.files_intake.analyze_image_bytes",
        return_value=_MOCK_IMAGE_ANALYSIS,
    ):
        with patch("builtins.open", side_effect=AssertionError("disk write attempted")):
            with patch(
                "pathlib.Path.write_bytes",
                side_effect=AssertionError("disk write attempted"),
            ):
                with patch(
                    "pathlib.Path.write_text",
                    side_effect=AssertionError("disk write attempted"),
                ):
                    r = _post_intake(client, headers, "safe.png", data, "image/png")

    assert r.status_code == 200
    assert r.json()["stored"] is False


# 10. verify /chat still works
def test_chat_still_works_after_intake_module_loaded(monkeypatch):
    monkeypatch.setenv("GUEST_DAILY_MESSAGE_LIMIT", "20")
    from app.settings import reload_settings

    reload_settings()
    _reset_guest()
    client = TestClient(app)
    headers = _guest_headers(client)

    def _fake_gen(**_kwargs):
        return {
            "output": "mock chat reply",
            "success": True,
            "provider": "mock",
            "status_code": 200,
        }

    with patch("app.api.chat.generate_response", side_effect=_fake_gen), patch(
        "app.api.chat.write_exchange",
        return_value=MemoryWriteResult(saved=False, reason="test_skip"),
    ):
        r = client.post("/chat", json={"message": "hello after intake"}, headers=headers)

    assert r.status_code == 200, r.text
    assert "mock chat reply" in r.json()["output"]
