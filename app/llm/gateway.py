from __future__ import annotations

import logging
import requests as http_requests

from app.provider_manager import PROVIDER_PRIORITY, get_provider_manager
from app.settings import Settings, get_settings

logger = logging.getLogger("openchawn.gateway")


def _extract_openai_response_text(data: dict) -> str:
    """
    Parse POST /v1/responses JSON. `output_text` est surtout exposé par les SDK ;
    en HTTP brut il faut agréger les blocs output_text dans output[].content.
    """
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


def _openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    timeout: float = 120.0,
) -> tuple[str, int | None, str | None]:
    b = base_url.rstrip("/")
    if not api_key:
        return "", None, "OPENAI_COMPAT_API_KEY_MISSING"
    try:
        r = http_requests.post(
            f"{b}/chat/completions",
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
            logger.warning(f"compat model={model} status={sc} body={preview}")
            return "", sc, preview or "OPENAI_COMPAT_REQUEST_FAILED"
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
        logger.warning(f"compat exception err={e.__class__.__name__}: {e}")
        return "", None, f"{e.__class__.__name__}: {e}"


def _openai_responses(
    s: Settings,
    system_prompt: str,
    user_message: str,
) -> tuple[str, int | None, str | None]:
    if not s.openai_api_key:
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
        content = _extract_openai_response_text(data)
        if not content:
            return "", sc, "OPENAI_EMPTY_RESPONSE"
        return content, sc, None
    except Exception as e:
        logger.warning(f"openai responses exception={e.__class__.__name__}: {e}")
        return "", None, f"{e.__class__.__name__}: {e}"


def _ollama_chat(
    s: Settings,
    system_prompt: str,
    user_message: str,
) -> tuple[str, int | None, str | None]:
    if not s.ollama_enabled:
        return "", None, "OLLAMA_DISABLED"
    base = (s.ollama_base_url or s.ollama_url or "").strip().rstrip("/")
    if not base:
        return "", None, "OLLAMA_URL_MISSING"
    try:
        r = http_requests.post(
            f"{base}/api/chat",
            json={
                "model": s.ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
            },
            timeout=120,
        )
        data = r.json()
        sc = r.status_code
        if not r.ok:
            preview = (r.text or "")[:200]
            logger.warning(f"ollama status={sc} body={preview}")
            return "", sc, preview or "OLLAMA_REQUEST_FAILED"
        content = (data.get("message", {}).get("content", "") or "").strip()
        if not content:
            return "", sc, "OLLAMA_EMPTY_RESPONSE"
        return content, sc, None
    except Exception as e:
        logger.warning(f"ollama exception={e.__class__.__name__}: {e}")
        return "", None, f"{e.__class__.__name__}: {e}"


def _dispatch(
    name: str,
    s: Settings,
    system_prompt: str,
    user_message: str,
) -> tuple[str, int | None, str | None]:
    if name == "openrouter":
        return _openai_compatible(
            base_url=s.openrouter_base_url,
            api_key=s.openrouter_api_key,
            model=s.openrouter_model,
            system_prompt=system_prompt,
            user_message=user_message,
        )
    if name == "openai":
        return _openai_responses(s, system_prompt, user_message)
    if name == "deepseek":
        return _openai_compatible(
            base_url=s.deepseek_base_url,
            api_key=s.deepseek_api_key,
            model=s.deepseek_model,
            system_prompt=system_prompt,
            user_message=user_message,
        )
    if name == "kimi":
        return _openai_compatible(
            base_url=s.kimi_effective_base,
            api_key=s.kimi_effective_key,
            model=s.kimi_effective_model,
            system_prompt=system_prompt,
            user_message=user_message,
        )
    if name == "infomaniak":
        if not s.infomaniak_base_url:
            return "", None, "INFOMANIAK_BASE_URL_MISSING"
        return _openai_compatible(
            base_url=s.infomaniak_base_url,
            api_key=s.infomaniak_api_key,
            model=s.infomaniak_model,
            system_prompt=system_prompt,
            user_message=user_message,
        )
    if name == "ollama":
        return _ollama_chat(s, system_prompt, user_message)
    return "", None, "UNKNOWN_PROVIDER"


def _try_order(provider_hint: str) -> list[str]:
    pm = get_provider_manager()
    base = pm.resolution_order()
    h = (provider_hint or "").strip().lower()
    if not h:
        return list(base)
    if h in base or h in PROVIDER_PRIORITY:
        return [h] + [x for x in base if x != h]
    return list(base)


def generate_response(*, system_prompt: str, user_message: str, provider_hint: str = "") -> dict[str, str | bool | int | None]:
    """
    Gateway : OpenRouter → OpenAI → DeepSeek → Kimi → Infomaniak → Ollama (si activé).
    """
    s = get_settings()
    seq = _try_order(provider_hint)

    last_err: str | None = None
    last_code: int | None = None

    for name in seq:
        text, code, err = _dispatch(name, s, system_prompt, user_message)
        if text:
            return {
                "output": text,
                "provider": name,
                "success": True,
                "status_code": code,
                "error": None,
            }
        if err:
            last_err = err
            last_code = code
            logger.info(f"provider_skip name={name} err={err}")

    detail = last_err or (
        "NO_LLM_CONFIGURED: aucune clé API utilisable parmi "
        "OPENROUTER_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, KIMI_API_KEY, "
        "INFOMANIAK_* ou Ollama activé en développement."
    )
    return {
        "output": "",
        "provider": "fallback",
        "success": False,
        "status_code": last_code,
        "error": detail,
    }
