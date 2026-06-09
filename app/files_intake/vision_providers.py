"""
File intake image analysis providers (V1).

Progressive routing: local/slm → kimi → openai (fallback).
Image generation is a separate module — never used for analysis.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

import requests

from app.files_intake.image_analysis import (
    ImageAnalysisError,
    ImageAnalysisResult,
    VisionUnavailableError,
    _SYSTEM_PROMPT,
    _data_url,
    _extract_json_object,
    _normalize_result,
)
from app.settings import get_settings

logger = logging.getLogger("openchawn.files_intake.vision.providers")

SUPPORTED_ANALYSIS_PROVIDER_IDS = frozenset({"openai", "kimi", "local", "slm"})
_LEGACY_SINGLE_PROVIDER_ENV = "FILE_INTAKE_VISION_PROVIDER"


@runtime_checkable
class ImageAnalysisProvider(Protocol):
    """Contract for image analysis backends (cloud or future local/SLM)."""

    provider_id: str

    def is_configured(self) -> bool: ...

    def analyze_image(
        self, *, payload: bytes, content_type: str, filename: str
    ) -> ImageAnalysisResult: ...


def _analysis_timeout() -> float:
    return float(os.getenv("FILE_INTAKE_VISION_TIMEOUT", "90"))


def _openai_analysis_model() -> str:
    s = get_settings()
    explicit = (s.image_analysis_openai_model or "").strip()
    if explicit:
        return explicit
    return (s.openai_model or "gpt-4o-mini").strip() or "gpt-4o-mini"


def _kimi_analysis_model() -> str:
    s = get_settings()
    explicit = (s.image_analysis_kimi_model or "").strip()
    if explicit:
        return explicit
    return "moonshot-v1-8k-vision-preview"


def _post_chat_vision(
    *,
    provider_id: str,
    api_key: str,
    base_url: str,
    model: str,
    payload: bytes,
    content_type: str,
    filename: str,
) -> ImageAnalysisResult:
    safe_name = (filename or "image").strip()[:120]
    url = f"{base_url.rstrip('/')}/chat/completions"
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
            timeout=_analysis_timeout(),
        )
    except requests.RequestException as exc:
        logger.warning(
            "%s vision request failed | error=%s", provider_id, exc.__class__.__name__
        )
        raise ImageAnalysisError(f"Appel vision échoué : {exc.__class__.__name__}") from exc

    if resp.status_code in {401, 403}:
        raise VisionUnavailableError(
            f"Analyse image indisponible : clé {provider_id} refusée ou non autorisée."
        )
    if not resp.ok:
        preview = (resp.text or "")[:240]
        logger.warning(
            "%s vision bad status | status=%s body=%s", provider_id, resp.status_code, preview
        )
        raise ImageAnalysisError(f"Analyse image échouée (HTTP {resp.status_code}).")

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
    return _normalize_result(parsed, provider=provider_id, model=model, raw_text=content)


class KimiImageAnalysisProvider:
    provider_id = "kimi"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool((s.kimi_effective_key or "").strip())

    def analyze_image(
        self, *, payload: bytes, content_type: str, filename: str
    ) -> ImageAnalysisResult:
        s = get_settings()
        api_key = (s.kimi_effective_key or "").strip()
        if not api_key:
            raise VisionUnavailableError(
                "Analyse image indisponible : KIMI_API_KEY non configurée sur le serveur."
            )
        base_url = (s.kimi_effective_base or "https://api.moonshot.ai/v1").rstrip("/")
        model = _kimi_analysis_model()
        result = _post_chat_vision(
            provider_id=self.provider_id,
            api_key=api_key,
            base_url=base_url,
            model=model,
            payload=payload,
            content_type=content_type,
            filename=filename,
        )
        logger.info(
            "image_analysis_v1 ok | provider=%s | filename=%s | model=%s | elements=%s",
            self.provider_id,
            (filename or "")[:64],
            model,
            len(result.detected_elements),
        )
        return result


class OpenAIImageAnalysisProvider:
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
        base_url = (s.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        model = _openai_analysis_model()
        result = _post_chat_vision(
            provider_id=self.provider_id,
            api_key=api_key,
            base_url=base_url,
            model=model,
            payload=payload,
            content_type=content_type,
            filename=filename,
        )
        logger.info(
            "image_analysis_v1 ok | provider=%s | filename=%s | model=%s | elements=%s",
            self.provider_id,
            (filename or "")[:64],
            model,
            len(result.detected_elements),
        )
        return result


class _UnimplementedLocalAnalysisProvider:
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


def get_image_analysis_provider(provider_id: str) -> ImageAnalysisProvider:
    pid = (provider_id or "").strip().lower()
    if pid == "kimi":
        return KimiImageAnalysisProvider()
    if pid == "openai":
        return OpenAIImageAnalysisProvider()
    if pid in {"local", "slm"}:
        return _UnimplementedLocalAnalysisProvider(pid)
    return OpenAIImageAnalysisProvider()


def parse_image_analysis_provider_order() -> list[str]:
    s = get_settings()
    raw = (s.image_analysis_provider_order or "local,kimi,openai").strip()
    seen: set[str] = set()
    order: list[str] = []
    for part in raw.split(","):
        pid = part.strip().lower()
        if not pid or pid in seen:
            continue
        if pid in SUPPORTED_ANALYSIS_PROVIDER_IDS:
            order.append(pid)
            seen.add(pid)
    if not order:
        return ["local", "kimi", "openai"]
    return order


def image_analysis_default_provider() -> str:
    raw = (get_settings().image_analysis_default_provider or "kimi").strip().lower()
    return raw if raw in SUPPORTED_ANALYSIS_PROVIDER_IDS else "kimi"


def image_analysis_fallback_provider() -> str:
    raw = (get_settings().image_analysis_fallback_provider or "openai").strip().lower()
    return raw if raw in SUPPORTED_ANALYSIS_PROVIDER_IDS else "openai"


def _legacy_single_provider_override() -> str | None:
    raw = (os.getenv(_LEGACY_SINGLE_PROVIDER_ENV) or "").strip().lower()
    if raw and raw in SUPPORTED_ANALYSIS_PROVIDER_IDS:
        return raw
    return None


def build_image_analysis_try_order(*, accuracy_level: str = "standard") -> list[str]:
    level = (accuracy_level or "standard").strip().lower()
    fallback = image_analysis_fallback_provider()

    legacy = _legacy_single_provider_override()
    if legacy:
        return [legacy]

    if level == "high_accuracy":
        order = parse_image_analysis_provider_order()
        rest = [p for p in order if p != fallback]
        return [fallback, *rest]

    order = parse_image_analysis_provider_order()
    default = image_analysis_default_provider()
    # Progressive cost strategy: economical order, default provider first when present.
    if default in order:
        prioritized = [default] + [p for p in order if p != default]
    else:
        prioritized = [default, *order]
    seen: set[str] = set()
    result: list[str] = []
    for pid in prioritized:
        if pid not in seen:
            result.append(pid)
            seen.add(pid)
    fb = image_analysis_fallback_provider()
    if fb not in seen:
        result.append(fb)
    return result


def any_image_analysis_provider_configured() -> bool:
    for pid in parse_image_analysis_provider_order():
        if get_image_analysis_provider(pid).is_configured():
            return True
    fb = image_analysis_fallback_provider()
    if fb not in parse_image_analysis_provider_order():
        return get_image_analysis_provider(fb).is_configured()
    return False


def analyze_image_with_provider_routing(
    *,
    payload: bytes,
    content_type: str,
    filename: str,
    accuracy_level: str = "standard",
) -> ImageAnalysisResult:
    """
    Route image analysis through progressive providers.
    Never calls image generation APIs.
    """
    logger.info("image_generation_not_used_for_analysis=true")

    try_order = build_image_analysis_try_order(accuracy_level=accuracy_level)
    default_provider = image_analysis_default_provider()
    fallback_provider = image_analysis_fallback_provider()
    errors: list[str] = []
    attempted: list[str] = []

    for provider_id in try_order:
        provider = get_image_analysis_provider(provider_id)
        if not provider.is_configured():
            logger.debug("image_analysis_provider_skip | provider=%s | reason=not_configured", provider_id)
            continue

        attempted.append(provider_id)
        logger.info("image_analysis_provider_selected | provider=%s | accuracy=%s", provider_id, accuracy_level)

        try:
            result = provider.analyze_image(
                payload=payload, content_type=content_type, filename=filename
            )
        except VisionUnavailableError as exc:
            errors.append(f"{provider_id}: {exc}")
            logger.warning("image_analysis_provider_unavailable | provider=%s", provider_id)
            continue
        except ImageAnalysisError as exc:
            errors.append(f"{provider_id}: {exc}")
            logger.warning(
                "image_analysis_provider_failed | provider=%s | error=%s",
                provider_id,
                exc.__class__.__name__,
            )
            continue

        fallback_used = (
            provider_id == fallback_provider
            and default_provider in attempted[:-1]
            and provider_id != default_provider
        )
        if fallback_used:
            logger.info(
                "image_analysis_fallback_used=true | from=%s | to=%s",
                default_provider,
                fallback_provider,
            )
        else:
            logger.info("image_analysis_fallback_used=false | provider=%s", provider_id)

        if fallback_used:
            return ImageAnalysisResult(
                description=result.description,
                detected_elements=result.detected_elements,
                clarification_question=result.clarification_question,
                provider=result.provider,
                model=result.model,
                raw_text=result.raw_text,
                fallback_used=True,
            )
        return result

    detail = "; ".join(errors) if errors else "aucun provider vision configuré"
    raise VisionUnavailableError(f"Analyse image indisponible : {detail}")


# ── Legacy aliases (tests / older imports) ─────────────────────────────

FileIntakeVisionProvider = ImageAnalysisProvider
OpenAIVisionProvider = OpenAIImageAnalysisProvider
SUPPORTED_VISION_PROVIDER_IDS = SUPPORTED_ANALYSIS_PROVIDER_IDS


def resolve_vision_provider_id() -> str:
    legacy = _legacy_single_provider_override()
    if legacy:
        return legacy
    return image_analysis_default_provider()


def get_vision_provider() -> ImageAnalysisProvider:
    return get_image_analysis_provider(resolve_vision_provider_id())
