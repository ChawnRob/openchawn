"""
Image generation providers — separate from image analysis.

Generation (e.g. DALL·E / images API) must never be used for file intake analysis.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

from app.settings import get_settings

logger = logging.getLogger("openchawn.files_intake.image_generation")

SUPPORTED_GENERATION_PROVIDER_IDS = frozenset({"openai"})


@runtime_checkable
class ImageGenerationProvider(Protocol):
    provider_id: str

    def is_configured(self) -> bool: ...

    def generate_image(self, *, prompt: str) -> bytes: ...


class OpenAIImageGenerationProvider:
    """OpenAI /images/generations — not used during intake analysis."""

    provider_id = "openai"

    def is_configured(self) -> bool:
        return bool((get_settings().openai_api_key or "").strip())

    def generate_image(self, *, prompt: str) -> bytes:
        import requests

        s = get_settings()
        api_key = (s.openai_api_key or "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing for image generation.")
        base_url = (s.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        model = (os.getenv("IMAGE_GENERATION_OPENAI_MODEL") or "dall-e-3").strip()
        resp = requests.post(
            f"{base_url}/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"},
            timeout=float(os.getenv("IMAGE_GENERATION_TIMEOUT", "120")),
        )
        resp.raise_for_status()
        data = resp.json()
        url = ((data.get("data") or [{}])[0] or {}).get("url") or ""
        if not url:
            raise RuntimeError("OpenAI image generation returned no URL.")
        img = requests.get(url, timeout=60)
        img.raise_for_status()
        return img.content


def resolve_image_generation_provider_id() -> str:
    raw = (get_settings().image_generation_provider or "openai").strip().lower()
    if raw in SUPPORTED_GENERATION_PROVIDER_IDS:
        return raw
    return "openai"


def get_image_generation_provider() -> ImageGenerationProvider:
    provider_id = resolve_image_generation_provider_id()
    if provider_id == "openai":
        return OpenAIImageGenerationProvider()
    return OpenAIImageGenerationProvider()
