from __future__ import annotations

import os
import logging
import requests as http_requests

from app.config import MODEL_PROVIDER

logger = logging.getLogger("openchawn.gateway")


def generate_response(*, system_prompt: str, user_message: str) -> dict[str, str | bool | int | None]:
    """
    Unified OpenChawn LLM gateway.

    Primary: OpenRouter si MODEL_PROVIDER=openrouter (ou vide) et OPENROUTER_API_KEY.
    Sinon ou sans clé : Ollama local (fallback gratuit).
    """
    def _openrouter_chat() -> tuple[str, int | None, str | None]:
        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            logger.warning("provider=openrouter missing_key=true")
            return "", None, "OPENROUTER_API_KEY_MISSING"
        base_url = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
        model = (os.getenv("OPENROUTER_MODEL") or "openrouter/auto").strip()
        try:
            r = http_requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                },
                timeout=120,
            )
            data = r.json()
            status_code = r.status_code
            if not r.ok:
                body_preview = (r.text or "")[:200]
                logger.warning(
                    f"provider=openrouter response_status={status_code} error_body={body_preview}"
                )
                return "", status_code, body_preview or "OPENROUTER_REQUEST_FAILED"
            logger.info(f"provider=openrouter response_status={status_code}")
            content = (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
            if not content:
                return "", status_code, "OPENROUTER_EMPTY_RESPONSE"
            return content, status_code, None
        except Exception as e:
            logger.warning(f"provider=openrouter exception={e.__class__.__name__}: {e}")
            return "", None, f"{e.__class__.__name__}: {e}"

    def _ollama_chat() -> tuple[str, int | None, str | None]:
        try:
            base = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
            model = (os.getenv("OLLAMA_MODEL") or "mistral:7b").strip()
            r = http_requests.post(
                f"{base}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                },
                timeout=120,
            )
            data = r.json()
            status_code = r.status_code
            if not r.ok:
                body_preview = (r.text or "")[:200]
                logger.warning(
                    f"provider=ollama response_status={status_code} error_body={body_preview}"
                )
                return "", status_code, body_preview or "OLLAMA_REQUEST_FAILED"
            logger.info(f"provider=ollama response_status={status_code}")
            content = (data.get("message", {}).get("content", "") or "").strip()
            if not content:
                return "", status_code, "OLLAMA_EMPTY_RESPONSE"
            return content, status_code, None
        except Exception as e:
            logger.warning(f"provider=ollama exception={e.__class__.__name__}: {e}")
            return "", None, f"{e.__class__.__name__}: {e}"

    response_text = ""
    provider_used = "none"
    status_code: int | None = None
    error: str | None = None

    has_openrouter_key = bool((os.getenv("OPENROUTER_API_KEY") or "").strip())
    use_openrouter = False
    if MODEL_PROVIDER == "ollama":
        use_openrouter = False
    elif MODEL_PROVIDER == "openrouter":
        use_openrouter = has_openrouter_key
    else:
        # vide ou inconnu : compat — OpenRouter si clé présente
        use_openrouter = has_openrouter_key

    if use_openrouter:
        logger.info("provider_tested=openrouter")
        response_text, status_code, error = _openrouter_chat()
        provider_used = "openrouter" if response_text else "none"

    if not response_text:
        logger.info("provider_tested=ollama")
        response_text, status_code, ollama_error = _ollama_chat()
        if ollama_error:
            error = ollama_error
        if response_text:
            provider_used = "ollama/mistral:7b"
        else:
            provider_used = "fallback"
            if not error:
                error = "NO_PROVIDER_RESPONSE"

    return {
        "output": response_text,
        "provider": provider_used,
        "success": bool(response_text),
        "status_code": status_code,
        "error": error,
    }
