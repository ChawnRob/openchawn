"""
LLM and web-search pricing registry for cost intelligence (P1.5-COST).

Unknown models return partial pricing (known components only, never invented rates).
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from app.routing.provider_capabilities import provider_capabilities

logger = logging.getLogger("openchawn.cost.pricing")

PricingStatus = Literal["complete", "partial", "unknown"]

# USD per 1k tokens: (input, output)
_DEFAULT_LLM_RATES: dict[str, dict[str, tuple[float, float]]] = {
    "groq": {
        "llama-3.1-8b-instant": (0.00005, 0.00008),
        "default": (0.00005, 0.00008),
    },
    "openai": {
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4o": (0.0025, 0.01),
        "default": (0.00035, 0.00105),
    },
    "kimi": {
        "kimi-k2-0905-preview": (0.00015, 0.0006),
        "default": (0.00022, 0.00088),
    },
    "mistral": {
        "mistral-small-latest": (0.0001, 0.0003),
        "default": (0.0001, 0.0003),
    },
    "deepseek": {
        "deepseek-v4-flash": (0.00007, 0.00011),
        "deepseek-v4-pro": (0.00014, 0.00028),
        "default": (0.00008, 0.00028),
    },
    "openrouter": {
        "default": (0.0002, 0.0008),
    },
    "local": {
        "default": (0.0, 0.0),
    },
    "tavily": {
        "default": (0.0, 0.0),
    },
}

# USD per search request
_DEFAULT_WEB_SEARCH_RATES: dict[str, float] = {
    "tavily": 0.008,
    "perplexity": 0.005,
    "default": 0.005,
}

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(0, len(text or "") // _CHARS_PER_TOKEN)


def _env_float(key: str) -> float | None:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _provider_fallback_per_1k(provider: str) -> tuple[float, float]:
    """Fallback from provider_capabilities blended rate (single rate → split 40/60 in/out)."""
    prov = (provider or "").strip().lower()
    cap = next(
        (x for x in provider_capabilities.values() if str(x.get("provider", "")).lower() == prov),
        None,
    )
    if cap:
        blended = float(cap.get("estimated_cost_per_1k_tokens_usd", 0.0))
        return blended * 0.4, blended * 0.6
    return 0.0, 0.0


def resolve_llm_rates(provider: str, model: str | None) -> tuple[float, float, PricingStatus]:
    prov = (provider or "").strip().lower() or "unknown"
    mdl = (model or "").strip().lower()

    env_in = _env_float(f"COST_{prov.upper()}_INPUT_PER_1K_USD")
    env_out = _env_float(f"COST_{prov.upper()}_OUTPUT_PER_1K_USD")
    if env_in is not None and env_out is not None:
        return env_in, env_out, "complete"

    rates = _DEFAULT_LLM_RATES.get(prov, {})
    if mdl and mdl in rates:
        inp, out = rates[mdl]
        return inp, out, "complete"
    if "default" in rates:
        inp, out = rates["default"]
        status: PricingStatus = "partial" if mdl else "complete"
        if mdl and mdl not in rates:
            logger.warning("cost_pricing unknown model | provider=%s | model=%s", prov, mdl)
        return inp, out, status

    if prov != "unknown" and prov != "none":
        inp, out = _provider_fallback_per_1k(prov)
        if inp or out:
            logger.warning("cost_pricing provider fallback | provider=%s | model=%s", prov, mdl or "(none)")
            return inp, out, "partial"

    if prov not in ("unknown", "none", ""):
        logger.warning("cost_pricing unknown provider | provider=%s", prov)
    return 0.0, 0.0, "unknown"


def compute_llm_cost_usd(
    *,
    provider: str | None,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    input_text: str = "",
    output_text: str = "",
) -> tuple[float, int | None, int | None, PricingStatus]:
    inp_tok = input_tokens if input_tokens is not None else estimate_tokens(input_text)
    out_tok = output_tokens if output_tokens is not None else estimate_tokens(output_text)
    in_rate, out_rate, status = resolve_llm_rates(provider or "", model)
    cost = (inp_tok / 1000.0) * in_rate + (out_tok / 1000.0) * out_rate
    if status == "unknown" and (provider or "").strip().lower() not in ("", "none", "unknown"):
        status = "partial"
    return round(max(0.0, cost), 8), inp_tok, out_tok, status


def resolve_web_search_rate(provider: str) -> tuple[float, PricingStatus]:
    prov = (provider or "").strip().lower() or "default"
    env_key = f"COST_{prov.upper()}_PER_SEARCH_USD"
    env_val = _env_float(env_key)
    if env_val is not None:
        return env_val, "complete"
    if prov in _DEFAULT_WEB_SEARCH_RATES:
        return _DEFAULT_WEB_SEARCH_RATES[prov], "complete"
    if prov != "default":
        logger.warning("cost_pricing unknown web provider | provider=%s", prov)
    return _DEFAULT_WEB_SEARCH_RATES.get("default", 0.0), "partial"


def compute_web_search_cost_usd(*, provider: str, count: int) -> tuple[float, PricingStatus]:
    if count <= 0:
        return 0.0, "complete"
    rate, status = resolve_web_search_rate(provider)
    return round(rate * count, 8), status


def merge_pricing_status(*statuses: PricingStatus) -> PricingStatus:
    if any(s == "unknown" for s in statuses):
        return "unknown"
    if any(s == "partial" for s in statuses):
        return "partial"
    return "complete"


def usd_to_eur(amount_usd: float) -> float:
    rate = _env_float("COST_USD_TO_EUR_RATE")
    if rate is None:
        rate = 0.92
    return round(amount_usd * rate, 6)
