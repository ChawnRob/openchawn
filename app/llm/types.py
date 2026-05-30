"""Shared LLM generation types (Phase 1 provider adapter refactor)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSelectionContext:
    system_prompt: str
    user_message: str
    provider_hint: str = ""


@dataclass(frozen=True)
class AdapterCompletion:
    text: str
    status_code: int | None
    error: str | None


@dataclass(frozen=True)
class ProviderResult:
    output: str
    provider: str
    success: bool
    status_code: int | None
    error: str | None
    prompt_contains_forced_french_before_sanitize: bool = False
    forced_french_runtime_removed: bool = False

    def to_dict(self) -> dict[str, str | bool | int | None]:
        return {
            "output": self.output,
            "provider": self.provider,
            "success": self.success,
            "status_code": self.status_code,
            "error": self.error,
            "prompt_contains_forced_french_before_sanitize": self.prompt_contains_forced_french_before_sanitize,
            "forced_french_runtime_removed": self.forced_french_runtime_removed,
        }
