"""
File intake vision provider interface (V1).

Default: OpenAI vision. Local/SLM providers can be plugged in later via
FILE_INTAKE_VISION_PROVIDER without changing the intake route contract.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from app.files_intake.image_analysis import (
    ImageAnalysisResult,
    VisionUnavailableError,
    _SYSTEM_PROMPT,
    _data_url,
    _extract_json_object,
    _normalize_result,
    _vision_model,
)
from app.settings import get_settings

import logging
import requests

logger = logging.getLogger("openchawn.files_intake.vision.providers")

SUPPORTED_VISION_PROVIDER_IDS = frozenset({"openai", "local", "slm"})


@runtime_checkable
class FileIntakeVisionProvider(Protocol):
    """Contract for image analysis backends (cloud or future local/SLM)."""

    provider_id: str

    def is_configured(self) -> bool: ...

    def analyze_image(
        self, *, payload: bytes, content_type: str, filename: str
    ) -> ImageAnalysisResult: ...


class OpenAIVisionProvider:
    provider_id = "openai"

    def is_configured(self) -> bool:
        return bool((get_settings().openai_api_key or "").strip())

    def analyze_image(
        self, *, payload: bytes, content_type: str, filename: str
    ) -> ImageAnalysisResult:
        s = get_settings()
        api_key = (s.openai_api_key or "").strip()
        if not api_key:
            raise VisionUnavailableError(
                "Analyse image indisponible : OPENAI_API_KEY non configurée sur le serveur."
            )

        model = _vision_model()
        base_url = (s.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        safe_name = (filename or "image").strip()[:120]

        body = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Analyse cette image (fichier : {safe_name}). "
                                "Retourne uniquement le JSON demandé."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": _data_url(content_type, payload)},
                        },
                    ],
                },
            ],
        }

        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=float(os.getenv("FILE_INTAKE_VISION_TIMEOUT", "90")),
            )
        except requests.RequestException as exc:
            logger.warning("openai vision request failed | error=%s", exc.__class__.__name__)
            from app.files_intake.image_analysis import ImageAnalysisError

            raise ImageAnalysisError(f"Appel vision échoué : {exc.__class__.__name__}") from exc

        if resp.status_code in {401, 403}:
            raise VisionUnavailableError(
                "Analyse image indisponible : clé OpenAI refusée ou non autorisée."
            )
        if not resp.ok:
            from app.files_intake.image_analysis import ImageAnalysisError

            preview = (resp.text or "")[:240]
            logger.warning("openai vision bad status | status=%s body=%s", resp.status_code, preview)
            raise ImageAnalysisError(f"Analyse image échouée (HTTP {resp.status_code}).")

        try:
            data = resp.json()
        except ValueError as exc:
            from app.files_intake.image_analysis import ImageAnalysisError

            raise ImageAnalysisError("Réponse vision invalide (JSON).") from exc

        choices = data.get("choices") or []
        content = ""
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            content = str(msg.get("content") or "").strip()

        parsed = _extract_json_object(content)
        result = _normalize_result(parsed, provider=self.provider_id, model=model, raw_text=content)
        logger.info(
            "image_analysis_v1 ok | provider=%s | filename=%s | model=%s | elements=%s",
            self.provider_id,
            safe_name[:64],
            model,
            len(result.detected_elements),
        )
        return result


class _UnimplementedLocalVisionProvider:
    """Placeholder for a future on-prem / SLM vision backend."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id

    def is_configured(self) -> bool:
        return False

    def analyze_image(
        self, *, payload: bytes, content_type: str, filename: str
    ) -> ImageAnalysisResult:
        raise VisionUnavailableError(
            f"Analyse image via provider '{self.provider_id}' non activée (SLM/local à venir)."
        )


def resolve_vision_provider_id() -> str:
    raw = (os.getenv("FILE_INTAKE_VISION_PROVIDER") or "openai").strip().lower()
    if raw in SUPPORTED_VISION_PROVIDER_IDS:
        return raw
    return "openai"


def get_vision_provider() -> FileIntakeVisionProvider:
    provider_id = resolve_vision_provider_id()
    if provider_id == "openai":
        return OpenAIVisionProvider()
    if provider_id in {"local", "slm"}:
        return _UnimplementedLocalVisionProvider(provider_id)
    return OpenAIVisionProvider()
