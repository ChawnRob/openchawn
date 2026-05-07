from __future__ import annotations

import logging
import os
import requests as http_requests

from app.provider_manager import FIXED_ORDER, get_provider_manager
from app.routing import (
    get_cost_tracking_hooks,
    get_fallback_manager,
    get_provider_health_hooks,
)
from app.routing.provider_capabilities import provider_capabilities
from app.settings import Settings, get_settings

logger = logging.getLogger("openchawn.gateway")


def _deepseek_api_key_live() -> str:
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def _deepseek_model_live() -> str:
    return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"


def _deepseek_model_for_task(task_type: str) -> str:
    # V11.6 policy: simple/volume -> Flash, reasoning -> Pro.
    t = (task_type or "").strip().lower()
    if t in {"reasoning", "analysis", "premium_tools", "complex"}:
        return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
    return "deepseek-v4-flash"


def _extract_openai_response_text(data: dict) -> str:
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


def _chat_completions(
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


def _openai_responses(
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
        content = _extract_openai_response_text(data)
        if not content:
            return "", sc, "OPENAI_EMPTY_RESPONSE"
        return content, sc, None
    except Exception as e:
        logger.warning(f"openai responses exception={e.__class__.__name__}: {e}")
        return "", None, f"{e.__class__.__name__}: {e}"


def _dispatch(
    name: str,
    s: Settings,
    system_prompt: str,
    user_message: str,
    task_type: str = "",
) -> tuple[str, int | None, str | None]:
    if name == "openrouter":
        return _chat_completions(
            base_url=s.openrouter_base_url,
            api_key=(s.openrouter_api_key or "").strip(),
            model=s.openrouter_model,
            system_prompt=system_prompt,
            user_message=user_message,
            log_label="openrouter",
        )
    if name == "openai":
        return _openai_responses(s, system_prompt, user_message)
    if name == "deepseek":
        if not _deepseek_api_key_live():
            return "", None, "DEEPSEEK_API_KEY_MISSING"
        return _chat_completions(
            base_url=s.deepseek_base_url,
            api_key=_deepseek_api_key_live(),
            model=_deepseek_model_for_task(task_type),
            system_prompt=system_prompt,
            user_message=user_message,
            log_label="deepseek",
        )
    if name == "kimi":
        key = (s.kimi_api_key or "").strip()
        if not key:
            return "", None, "KIMI_API_KEY_MISSING"
        base = (s.kimi_base_url or "").strip().rstrip("/") or "https://api.moonshot.ai/v1"
        kem = (s.kimi_model or "").strip() or "kimi-k2-0905-preview"
        return _chat_completions(
            base_url=base,
            api_key=key,
            model=kem,
            system_prompt=system_prompt,
            user_message=user_message,
            log_label="kimi",
        )
    if name == "infomaniak":
        if not (s.infomaniak_api_key or "").strip():
            return "", None, "INFOMANIAK_API_KEY_MISSING"
        if not (s.infomaniak_model or "").strip():
            return "", None, "INFOMANIAK_MODEL_MISSING"
        if not (s.infomaniak_base_url or "").strip():
            return "", None, "INFOMANIAK_BASE_URL_MISSING"
        return _chat_completions(
            base_url=(s.infomaniak_base_url or "").strip().rstrip("/"),
            api_key=(s.infomaniak_api_key or "").strip(),
            model=(s.infomaniak_model or "").strip(),
            system_prompt=system_prompt,
            user_message=user_message,
            log_label="infomaniak",
        )
    return "", None, "UNKNOWN_PROVIDER"


def _hint_order(pm, provider_hint: str) -> list[str]:
    base = pm.resolution_order()
    h = (provider_hint or "").strip().lower()
    if not h:
        return base
    if h in FIXED_ORDER:
        extra = pm.settings
        hint_ok = (
            (h == "deepseek" and bool(_deepseek_api_key_live()))
            or (h == "kimi" and bool((extra.kimi_api_key or "").strip()))
            or (h == "openrouter" and bool((extra.openrouter_api_key or "").strip()))
            or (h == "openai" and bool((extra.openai_api_key or "").strip()))
            or (h == "infomaniak" and bool((extra.infomaniak_api_key or "").strip()))
        )
        if hint_ok:
            return [h] + [x for x in base if x != h]
    return base


def _estimate_cost(provider: str, text: str) -> tuple[int, float]:
    tokens = max(1, len(text or "") // 4)
    cap = next((x for x in provider_capabilities.values() if str(x.get("provider", "")) == provider), None)
    if not cap:
        return tokens, 0.0
    estimated = (tokens / 1000.0) * float(cap.get("estimated_cost_per_1k_tokens_usd", 0.0))
    return tokens, estimated


def generate_response(*, system_prompt: str, user_message: str, provider_hint: str = "") -> dict[str, str | bool | int | None]:
    """
    Chaîne **explicite uniquement parmi providers configurés** :
    ordre intelligent DeepSeek/Kimi/OpenAI/Infomaniak (avec OpenRouter en compat).

    Pas d’Ollama. Pas de tentative si DEFAULT_PROVIDER=deepseek sans DEEPSEEK_API_KEY.
    """
    s = get_settings()
    pm = get_provider_manager()

    if _normalize_pref(s.default_provider) == "deepseek" and not _deepseek_api_key_live():
        return {
            "output": "",
            "provider": "none",
            "success": False,
            "status_code": None,
            "error": "DeepSeek API key missing",
        }

    decision = pm.intelligent_decision(
        system_prompt=system_prompt,
        user_message=user_message,
        provider_hint=provider_hint,
    )
    seq = decision.ordered_providers

    if not seq:
        return {
            "output": "",
            "provider": "none",
            "success": False,
            "status_code": None,
            "error": "Aucune clé API LLM configurée (DEEPSEEK requis par défaut, puis KIMI/OPENAI/INFOMANIAK optionnels).",
        }

    last_err: str | None = None
    last_code: int | None = None
    fallback = get_fallback_manager()
    health = get_provider_health_hooks()
    cost = get_cost_tracking_hooks()

    for name in seq:
        text, code, err = _dispatch(
            name,
            s,
            system_prompt,
            user_message,
            task_type=decision.task_type,
        )
        if text:
            health.mark_success(name)
            estimated_tokens, estimated_cost = _estimate_cost(name, system_prompt + user_message + text)
            cost.track(name, estimated_tokens, estimated_cost)
            return {
                "output": text,
                "provider": name,
                "success": True,
                "status_code": code,
                "error": None,
            }
        if err:
            health.mark_failure(name)
            fallback.record(name, err)
            last_err = err
            last_code = code
            logger.info(f"provider_fail name={name} err={err}")

    detail = last_err or "Échec de tous les providers configurés."
    return {
        "output": "",
        "provider": "none",
        "success": False,
        "status_code": last_code,
        "error": detail,
    }


def _normalize_pref(x: str) -> str:
    return (x or "").strip().lower()
