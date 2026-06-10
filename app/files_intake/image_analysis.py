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
- description (string): rich plain-language summary (subject, context, packaging if any)
- detected_elements (array of strings): objects, UI, brands, categories, short text snippets
- visible_text (array of strings): legible text transcribed from labels, boxes, screens (empty if none)
- probable_subject (string): what the scene/product most likely is (use packaging text when present)
- likely_use (string or null): probable intended use in everyday terms
- safety_notes (string or null): cautious notes for health/wellness/medical-looking items — no diagnosis or strong medical promises
- uncertainties (string or null): what remains ambiguous
- clarification_question (string or null): one short follow-up if important; otherwise null

Rules:
- Read and exploit visible text on packaging, boxes, and labels before guessing from generic shapes.
- If text says cupping, ventouses, glass cups for therapy, etc., do NOT describe as disposable plastic drink cups.
- Be factual. Do not invent unreadable text.
- Prefer French for description and questions when the UI is French."""


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

    visible_text: list[str] = []
    vt_raw = data.get("visible_text") or []
    if isinstance(vt_raw, list):
        for item in vt_raw:
            s = str(item or "").strip()
            if s:
                visible_text.append(s)

    probable_subject = str(data.get("probable_subject") or "").strip()
    likely_use = str(data.get("likely_use") or "").strip() or None
    safety_notes = str(data.get("safety_notes") or "").strip() or None
    uncertainties = str(data.get("uncertainties") or "").strip() or None

    enriched_elements = list(detected)
    if visible_text:
        enriched_elements.append("texte visible : " + "; ".join(visible_text[:6]))
    if probable_subject and probable_subject not in description:
        enriched_elements.append("sujet probable : " + probable_subject)
    if likely_use:
        enriched_elements.append("usage probable : " + likely_use)
    if safety_notes:
        enriched_elements.append("prudence : " + safety_notes)
    if uncertainties:
        enriched_elements.append("incertitudes : " + uncertainties)

    rich_description = description
    if probable_subject and probable_subject.lower() not in rich_description.lower():
        rich_description = f"{probable_subject}. {rich_description}"

    return ImageAnalysisResult(
        description=rich_description,
        detected_elements=enriched_elements,
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
