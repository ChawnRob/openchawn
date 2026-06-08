"""
Image analysis V1 for COCO file intake.

Uses OpenAI-compatible chat/completions with a vision message. No disk persistence.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from app.settings import get_settings

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
            "analysis_version": ANALYSIS_VERSION,
        }


def vision_provider_configured() -> bool:
    s = get_settings()
    return bool((s.openai_api_key or "").strip())


def _vision_model() -> str:
    explicit = (os.getenv("FILE_INTAKE_VISION_MODEL") or "").strip()
    if explicit:
        return explicit
    s = get_settings()
    return (s.openai_model or "gpt-4o-mini").strip() or "gpt-4o-mini"


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
    )


def analyze_image_bytes(*, payload: bytes, content_type: str, filename: str) -> ImageAnalysisResult:
    """
    Run vision analysis on in-memory image bytes.

    Raises VisionUnavailableError if OpenAI key is missing.
    Raises ImageAnalysisError on provider/parse failures.
    """
    if content_type not in IMAGE_MIME_TYPES:
        raise ImageAnalysisError(f"Type non supporté pour l'analyse image : {content_type}")

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
        logger.warning("vision request failed | error=%s", exc.__class__.__name__)
        raise ImageAnalysisError(f"Appel vision échoué : {exc.__class__.__name__}") from exc

    if resp.status_code in {401, 403}:
        raise VisionUnavailableError(
            "Analyse image indisponible : clé OpenAI refusée ou non autorisée."
        )
    if not resp.ok:
        preview = (resp.text or "")[:240]
        logger.warning("vision bad status | status=%s body=%s", resp.status_code, preview)
        raise ImageAnalysisError(
            f"Analyse image échouée (HTTP {resp.status_code})."
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise ImageAnalysisError("Réponse vision invalide (JSON).") from exc

    choices = data.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "").strip()

    parsed = _extract_json_object(content)
    result = _normalize_result(parsed, provider="openai", model=model, raw_text=content)
    logger.info(
        "image_analysis_v1 ok | filename=%s | model=%s | elements=%s",
        safe_name[:64],
        model,
        len(result.detected_elements),
    )
    return result
