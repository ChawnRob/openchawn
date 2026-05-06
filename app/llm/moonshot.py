from __future__ import annotations

from typing import Any

import httpx

from app.settings import get_settings

_DEFAULT_BASE = "https://api.moonshot.cn/v1"
_DEFAULT_MODEL = "kimi-k2.6-9b"
_DEFAULT_TIMEOUT = 120.0


def moonshot_chat_completion(
    *,
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    timeout: float | None = None,
) -> str:
    """
    Appelle l'API OpenAI-compatible Moonshot (chat/completions).

    Retourne le texte assistant, ou une chaîne vide si la clé est absente
    ou si l'appel échoue (le caller peut alors basculer sur Ollama).
    """
    s = get_settings()
    api_key = (s.moonshot_api_key or "").strip()
    if not api_key:
        return ""

    base = (s.moonshot_base_url or _DEFAULT_BASE).rstrip("/")
    m = (model or s.moonshot_model or _DEFAULT_MODEL).strip()
    t = timeout if timeout is not None else float(s.moonshot_timeout or _DEFAULT_TIMEOUT)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    payload: dict[str, Any] = {
        "model": m,
        "messages": messages,
        "stream": False,
    }

    url = f"{base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=t) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError):
        return ""

    try:
        text = data["choices"][0]["message"]["content"]
        if isinstance(text, str):
            return text.strip()
    except (KeyError, IndexError, TypeError):
        pass
    return ""
