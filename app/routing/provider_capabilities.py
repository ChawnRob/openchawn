from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapability:
    key: str
    provider: str
    model: str
    priority: int
    estimated_cost_per_1k_tokens_usd: float
    max_context_tokens: int
    reasoning_score: int
    availability_tier: str
    enterprise_sovereign_ready: bool
    task_profiles: tuple[str, ...]


provider_capabilities: dict[str, ProviderCapability] = {
    "deepseek_flash": ProviderCapability(
        key="deepseek_flash",
        provider="deepseek",
        model="deepseek-v4-flash",
        priority=100,
        estimated_cost_per_1k_tokens_usd=0.08,
        max_context_tokens=128000,
        reasoning_score=62,
        availability_tier="primary",
        enterprise_sovereign_ready=False,
        task_profiles=("economy", "simple", "fallback"),
    ),
    "deepseek_pro": ProviderCapability(
        key="deepseek_pro",
        provider="deepseek",
        model="deepseek-v4-pro",
        priority=95,
        estimated_cost_per_1k_tokens_usd=0.28,
        max_context_tokens=128000,
        reasoning_score=86,
        availability_tier="primary",
        enterprise_sovereign_ready=False,
        task_profiles=("reasoning", "analysis"),
    ),
    "kimi": ProviderCapability(
        key="kimi",
        provider="kimi",
        model="kimi-k2-0905-preview",
        priority=88,
        estimated_cost_per_1k_tokens_usd=0.22,
        max_context_tokens=200000,
        reasoning_score=84,
        availability_tier="secondary",
        enterprise_sovereign_ready=False,
        task_profiles=("long_context", "agentic", "analysis"),
    ),
    "openai": ProviderCapability(
        key="openai",
        provider="openai",
        model="gpt-4o-mini",
        priority=80,
        estimated_cost_per_1k_tokens_usd=0.35,
        max_context_tokens=128000,
        reasoning_score=90,
        availability_tier="secondary",
        enterprise_sovereign_ready=False,
        task_profiles=("premium_tools", "complex", "reasoning"),
    ),
    "infomaniak": ProviderCapability(
        key="infomaniak",
        provider="infomaniak",
        model="",
        priority=78,
        estimated_cost_per_1k_tokens_usd=0.30,
        max_context_tokens=64000,
        reasoning_score=75,
        availability_tier="european_layer",
        enterprise_sovereign_ready=True,
        task_profiles=("enterprise_sovereign", "compliance"),
    ),
}

