from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.auth.deps import get_current_user_or_guest
from app.auth.guest import check_guest_quota
from app.config import MAX_MESSAGE_LENGTH
from app.core.initial_rules import build_runtime_rules_prompt
from app.core.language_policy import (
    build_language_instruction,
    detect_explicit_language_request,
    detect_user_language,
    normalize_language_code,
)
from app.core.runtime_language_guard import (
    prompt_contains_forced_french,
    sanitize_provider_prompts,
)
from app.llm import generate_response
from app.memory import memory_consolidation_scheduler as memory_consolidation
from app.memory.fractal_memory import build_layered_memory_context, write_exchange
from app.profiles import PROFILES, get_profile

logger = logging.getLogger("openchawn.chat")

router = APIRouter(tags=["openchawn"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    profile: str = ""
    provider: str = ""
    project_name: str = ""
    memory_context: str = ""
    user_goal: str = ""

    @field_validator("message")
    @classmethod
    def validate_message_guardrails(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Message vide")
        if len(v) > 2000:
            raise ValueError("Message trop long (2000 caractères max)")
        return v


def resolve_profile_id(req: ChatRequest, user: dict) -> str:
    raw = (req.profile or "").strip().lower()
    if raw and raw in PROFILES:
        return raw
    if user.get("is_guest"):
        return "default"
    bt = str(user.get("business_type") or "default").strip().lower()
    return bt if bt in PROFILES else "default"


def effective_response_language_hint(message: str) -> str:
    dr = detect_explicit_language_request(message or "")
    lang = (dr or {}).get("language")
    if lang:
        return normalize_language_code(str(lang))
    return normalize_language_code(detect_user_language(message or ""))


def infer_forced_french_source_type(*, memory_body: str, profile_prompt: str, system_core: str) -> str:
    if prompt_contains_forced_french(memory_body):
        return "memory"
    if prompt_contains_forced_french(profile_prompt):
        return "profile"
    if prompt_contains_forced_french(system_core):
        return "system"
    return "unknown"


def build_openchawn_base_system_prompt() -> str:
    return (
        "You are OpenChawn, an AI orchestration system created by Robert L. "
        "STRICT RULES: "
        "1. Follow the language instruction injected at the top of the user message with highest priority "
        "(including translation and explicit-language exceptions). "
        "2. Keep answers concise and direct. "
        "3. Never mention model providers or engine names. "
        "4. Identity is OpenChawn."
    )


def assemble_chat_generation_inputs(
    req: ChatRequest,
    *,
    user: dict,
    persist_memory_side_effects: bool = True,
) -> dict[str, Any]:
    proj_hint = (req.project_name or "").strip()
    if user.get("is_guest"):
        user_key = f"guest-{(user.get('guest_session_id') or '')[:28]}"
    else:
        user_key = f"user-{user.get('id', '')}"

    profile_id = resolve_profile_id(req, user)
    profile = get_profile(profile_id)
    profile_prompt = str(profile.get("system_prompt") or "").strip()

    memory_used = False
    memory_context, memories = build_layered_memory_context(
        req.message,
        user_key=user_key,
        project_name_hint=proj_hint,
        is_guest=bool(user.get("is_guest")),
        persist_memory_side_effects=persist_memory_side_effects,
    )
    if memory_context:
        memory_used = True

    base_request = req.message
    if memory_context:
        final_prompt = f"{memory_context}\n\n── DEMANDE ──\n{base_request}"
    else:
        final_prompt = base_request

    extra_parts = []
    if req.project_name:
        extra_parts.append(f"Project: {req.project_name}")
    if req.memory_context:
        extra_parts.append(f"Memory: {req.memory_context}")
    if req.user_goal:
        extra_parts.append(f"UserGoal: {req.user_goal}")
    if extra_parts:
        final_prompt = "\n".join(extra_parts) + "\n\n" + final_prompt

    lang_instruction = build_language_instruction(req.message)
    layered_user_message = f"{lang_instruction}\n\n{final_prompt}"

    base_system = build_openchawn_base_system_prompt()
    runtime_rules = build_runtime_rules_prompt()
    if runtime_rules:
        base_system = f"{base_system}\n\nRuntimeRules:\n{runtime_rules}"

    system_prompt = f"{profile_prompt}\n\n{base_system}" if profile_prompt else base_system

    detected_lang = detect_user_language(req.message or "")
    hint_lang = effective_response_language_hint(req.message or "")

    pre_combined_scan = (system_prompt + "\n" + layered_user_message).strip()
    forced_french_runtime_detected = bool(prompt_contains_forced_french(pre_combined_scan))

    sp_san, um_san, forced_french_runtime_removed = sanitize_provider_prompts(
        system_prompt, layered_user_message
    )

    return {
        "user_key": user_key,
        "profile_used": profile_id,
        "profile_prompt": profile_prompt,
        "memory_used": memory_used,
        "memory_count": len(memories),
        "memory_context_plain": memory_context,
        "detected_language": detected_lang,
        "final_language_hint": hint_lang,
        "lang_instruction": lang_instruction,
        "system_prompt": system_prompt,
        "user_message": layered_user_message,
        "sanitized_system_prompt": sp_san,
        "sanitized_user_message": um_san,
        "forced_french_runtime_detected": forced_french_runtime_detected,
        "forced_french_runtime_removed_preview": forced_french_runtime_removed,
        "forced_french_source_type": infer_forced_french_source_type(
            memory_body=memory_context,
            profile_prompt=profile_prompt,
            system_core=base_system,
        ),
        "prompt_contains_forced_french": bool(prompt_contains_forced_french(pre_combined_scan)),
    }


@router.post("/chat")
def chat(
    req: ChatRequest,
    user: dict = Depends(get_current_user_or_guest),
    debug: bool = Query(default=False),
):
    is_guest = user.get("is_guest", False)

    if is_guest:
        quota = check_guest_quota(user["guest_session_id"], user["ip"])
        if not quota["allowed"]:
            logger.warning(
                f"guest quota blocked | ip={user['ip']} | "
                f"session={user['guest_session_id'][:12]}…"
            )
            raise HTTPException(
                status_code=429,
                detail="Vous avez atteint la limite gratuite. Créez un compte pour continuer.",
            )

    bundle = assemble_chat_generation_inputs(req, user=user, persist_memory_side_effects=True)
    provider_hint = (req.provider or "").strip().lower()

    llm_result = generate_response(
        system_prompt=bundle["system_prompt"],
        user_message=bundle["user_message"],
        provider_hint=provider_hint,
    )
    response_text = llm_result.get("output", "")
    provider_used = llm_result.get("provider", "fallback")
    success = bool(llm_result.get("success", bool(response_text)))
    provider_error = llm_result.get("error", None)
    provider_status = llm_result.get("status_code", None)
    ff_removed = bool(llm_result.get("forced_french_runtime_removed", False))
    pre_ff = bool(llm_result.get("prompt_contains_forced_french_before_sanitize", False))

    logger.info(
        f"chat provider={provider_used} success={success} "
        f"status={provider_status} guest={is_guest} "
        f"forced_french_before={pre_ff} runtime_removed={ff_removed}"
    )

    if not success or not response_text:
        detail = "Provider indisponible."
        if provider_error:
            detail = f"Provider indisponible: {provider_error}"
        logger.warning(
            f"chat provider failed | provider={provider_used} "
            f"status={provider_status} error={provider_error}"
        )
        raise HTTPException(status_code=503, detail=detail)

    source = "chat_guest" if is_guest else "chat_user"
    write_result = write_exchange(
        source=source,
        user_message=req.message,
        assistant_response=response_text,
        project=req.project_name,
        user_key=str(bundle["user_key"]),
        project_name_hint=(req.project_name or "").strip(),
        is_guest=is_guest,
    )
    if write_result.saved:
        logger.info("chat memory writeback status=saved entries=%s", len(write_result.entry_ids))
    else:
        logger.info("chat memory writeback status=skipped reason=%s", write_result.reason or "unknown")

    try:
        consolidation_plan = memory_consolidation.build_consolidation_plan()
        consolidation_recommended = bool(
            consolidation_plan.get("status") == "ok" and consolidation_plan.get("should_run")
        )
    except Exception:
        consolidation_recommended = False

    result = {
        "output": response_text,
        "memory_used": bool(bundle["memory_used"]),
        "consolidation_recommended": consolidation_recommended,
        "lang": bundle.get("final_language_hint") or bundle.get("detected_language"),
        "profile_used": bundle["profile_used"],
    }
    if is_guest:
        result["guest"] = True
        result["quota_remaining"] = quota["remaining"]
    if debug:
        result["language_debug"] = {
            "route_used": "POST /chat",
            "profile_used": bundle["profile_used"],
            "detected_language": bundle["detected_language"],
            "final_language_instruction": (str(bundle.get("lang_instruction") or ""))[:420],
            "final_language": bundle.get("final_language_hint"),
            "forced_french_runtime_detected": bool(bundle.get("forced_french_runtime_detected")),
            "forced_french_runtime_removed": ff_removed,
            "forced_french_source_type": bundle.get("forced_french_source_type"),
            "prompt_contains_forced_french": bool(bundle.get("prompt_contains_forced_french")),
        }
    return result
