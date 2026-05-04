from __future__ import annotations

import os
import requests as http_requests

def generate_response(*, system_prompt: str, user_message: str) -> dict[str, str]:
    """
    Unified OpenChawn LLM gateway.

    Primary: OpenRouter (cloud, OpenAI-compatible API)
    Fallback: Ollama local
    """
    def _openrouter_chat() -> str:
        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            return ""
        base_url = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
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
            r.raise_for_status()
            data = r.json()
            return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
        except Exception:
            return ""

    def _ollama_chat() -> str:
        try:
            r = http_requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": "mistral:7b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                },
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            return (data.get("message", {}).get("content", "") or "").strip()
        except Exception:
            return ""

    response_text = ""
    provider_used = "none"

    has_openrouter_key = bool((os.getenv("OPENROUTER_API_KEY") or "").strip())
    if has_openrouter_key:
        response_text = _openrouter_chat()
        provider_used = "openrouter" if response_text else "none"

    if not response_text:
        response_text = _ollama_chat()
        if response_text:
            provider_used = "ollama/mistral:7b"
        elif provider_used == "none":
            provider_used = "fallback"

    if not response_text or response_text.strip() in ["", "None"]:
        response_text = "Je suis OpenChawn. Aucun modèle n'a répondu."
        provider_used = "fallback"

    return {
        "output": response_text,
        "provider": provider_used,
    }
