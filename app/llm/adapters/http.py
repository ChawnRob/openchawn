"""Shared HTTP helpers for chat provider adapters."""

from __future__ import annotations

import logging

import requests as http_requests

from app.settings import Settings

logger = logging.getLogger("openchawn.gateway")


def extract_openai_response_text(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    agg = (data.get("output_text") or "").strip()
    if agg:
        return agg
    texts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for block in item.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "output_text":
                t = block.get("text")
                if t:
                    texts.append(str(t))
    return "\n".join(texts).strip()


def chat_completions(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    timeout: float = 120.0,
    log_label: str = "compat",
) -> tuple[str, int | None, str | None]:
    """POST {base_url}/chat/completions (sans ajouter /v1 à la base)."""
    b = (base_url or "").strip().rstrip("/")
    if not api_key:
        return "", None, "OPENAI_COMPAT_API_KEY_MISSING"
    url = f"{b}/chat/completions"
    try:
        r = http_requests.post(
            url,
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
            timeout=timeout,
        )
        sc = r.status_code
        if not r.ok:
            preview = (r.text or "")[:240]
            logger.warning(f"{log_label} model={model} status={sc} body={preview}")
            return "", sc, preview or "CHAT_COMPLETIONS_REQUEST_FAILED"
        data = r.json()
        content = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
            or ""
        ).strip()
        if not content:
            return "", sc, "EMPTY_RESPONSE"
        return content, sc, None
    except Exception as e:
        logger.warning(f"{log_label} exception={e.__class__.__name__}: {e}")
        return "", None, f"{e.__class__.__name__}: {e}"


def openai_responses(
    s: Settings,
    system_prompt: str,
    user_message: str,
) -> tuple[str, int | None, str | None]:
    if not (s.openai_api_key or "").strip():
        return "", None, "OPENAI_API_KEY_MISSING"
    base_url = s.openai_base_url.rstrip("/")
    body: dict = {
        "model": s.openai_model,
        "input": user_message,
    }
    if s.openai_prompt_id:
        pv_raw = (s.openai_prompt_version or "1").strip()
        try:
            prompt_version: int | str = int(pv_raw)
        except (ValueError, TypeError):
            prompt_version = pv_raw or "1"
        body["prompt"] = {
            "id": s.openai_prompt_id.strip(),
            "version": prompt_version,
        }
        body["input"] = user_message
    else:
        body["instructions"] = system_prompt

    try:
        r = http_requests.post(
            f"{base_url}/responses",
            headers={
                "Authorization": f"Bearer {s.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
        sc = r.status_code
        if not r.ok:
            preview = (r.text or "")[:200]
            logger.warning(f"openai responses status={sc} body={preview}")
            return "", sc, preview or "OPENAI_REQUEST_FAILED"
        data = r.json()
        logger.info(f"openai responses status={sc} model={s.openai_model}")
        content = extract_openai_response_text(data)
        if not content:
            return "", sc, "OPENAI_EMPTY_RESPONSE"
        return content, sc, None
    except Exception as e:
        logger.warning(f"openai responses exception={e.__class__.__name__}: {e}")
        return "", None, f"{e.__class__.__name__}: {e}"
