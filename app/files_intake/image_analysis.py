"""
Image analysis V1 for COCO file intake.

Routes analysis through progressive vision providers (kimi default, openai fallback).
Image generation is never used for analysis.
No disk persistence.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("openchawn.files_intake.vision")

ANALYSIS_VERSION = "image_analysis_v1"
IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})

_SYSTEM_PROMPT = """You analyze a single user-uploaded image for OpenChawn COCO file intake V1.
Respond with ONE JSON object only (no markdown), keys:
- description (string): concise plain-language description of the image
- detected_elements (array of strings): notable objects, text, UI, people, documents, labels
- clarification_question (string or null): one short follow-up question if something important is unclear; otherwise null

Be factual. Do not invent unreadable text. Prefer French for description and questions when the UI is French."""


class VisionUnavailableError(RuntimeError):
    """Vision provider is not configured or cannot be used."""


class ImageAnalysisError(RuntimeError):
    """Vision call failed after provider was selected."""


@dataclass(frozen=True)
class ImageAnalysisResult:
    description: str
    detected_elements: list[str]
    clarification_question: str | None
    provider: str
    model: str
    raw_text: str
    fallback_used: bool = False

    def to_message(self) -> str:
        lines = [f"Description : {self.description}"]
        if self.detected_elements:
            lines.append("Éléments détectés : " + ", ".join(self.detected_elements))
        if self.clarification_question:
            lines.append("Pour aller plus loin : " + self.clarification_question)
        return "\n".join(lines)

    def to_payload(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "detected_elements": self.detected_elements,
            "clarification_question": self.clarification_question,
            "provider": self.provider,
            "model": self.model,
            "provider_used": self.provider,
            "model_used": self.model,
            "fallback_used": self.fallback_used,
            "analysis_version": ANALYSIS_VERSION,
        }


def vision_provider_configured() -> bool:
    from app.files_intake.vision_providers import any_image_analysis_provider_configured

    return any_image_analysis_provider_configured()


def _data_url(content_type: str, payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ImageAnalysisError("Réponse vision vide.")
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    raise ImageAnalysisError("Réponse vision non structurée.")


def _normalize_result(data: dict[str, Any], *, provider: str, model: str, raw_text: str) -> ImageAnalysisResult:
    description = str(data.get("description") or "").strip()
    if not description:
        raise ImageAnalysisError("Description image manquante dans la réponse vision.")

    elements_raw = data.get("detected_elements") or []
    detected: list[str] = []
    if isinstance(elements_raw, list):
        for item in elements_raw:
            s = str(item or "").strip()
            if s:
                detected.append(s)

    clar_raw = data.get("clarification_question")
    clarification = str(clar_raw).strip() if clar_raw not in (None, "") else None

    return ImageAnalysisResult(
        description=description,
        detected_elements=detected,
        clarification_question=clarification,
        provider=provider,
        model=model,
        raw_text=raw_text,
        fallback_used=False,
    )


def analyze_image_bytes(
    *,
    payload: bytes,
    content_type: str,
    filename: str,
    accuracy_level: str = "standard",
) -> ImageAnalysisResult:
    """
    Run vision analysis on in-memory image bytes via progressive provider routing.

    Raises VisionUnavailableError if no provider is configured.
    Raises ImageAnalysisError on provider/parse failures after all retries.
    """
    if content_type not in IMAGE_MIME_TYPES:
        raise ImageAnalysisError(f"Type non supporté pour l'analyse image : {content_type}")

    from app.files_intake.vision_providers import analyze_image_with_provider_routing

    if not vision_provider_configured():
        raise VisionUnavailableError(
            "Analyse image indisponible : aucun provider d'analyse image configuré sur le serveur."
        )
    return analyze_image_with_provider_routing(
        payload=payload,
        content_type=content_type,
        filename=filename,
        accuracy_level=accuracy_level,
    )
