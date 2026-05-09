from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.auth.deps import get_current_user_or_guest
from app.auth.guest import check_guest_quota
from app.config import MAX_MESSAGE_LENGTH
from app.core.initial_rules import build_runtime_rules_prompt
from app.core.language_policy import (
    build_language_instruction,
    detect_user_language,
    derive_response_language_trace,
)
from app.core.runtime_language_policy import OPENCHAWN_RUNTIME_LANGUAGE_POLICY_EN
from app.core.runtime_language_guard import (
    assistant_reply_violates_english_user_expectation,
    prompt_contains_forced_french,
    sanitize_provider_prompts,
)
from app.llm import generate_response
from app.memory import memory_consolidation_scheduler as memory_consolidation
from app.memory.fractal_memory import build_layered_memory_context, write_exchange
from app.profiles import PROFILES, get_profile

logger = logging.getLogger("openchawn.chat")

router = APIRouter(tags=["openchawn"])

CHAT_HANDLER_NAME = "handle_chat_request"
CHAT_PIPELINE_TAG = "v116-stabilization"

# Marqueurs durs diagnostic prod (présence dans JSON = trafic sur ce handler).
ROUTE_SIGNATURE_POST_CHAT = "POST_CHAT_MAIN_HANDLER_ACTIVE_V116"
ROUTE_SIGNATURE_POST_API_CHAT = "POST_API_CHAT_HANDLER_ACTIVE_V116"

# Ligne injectée système — identique à ``language_policy_version`` exposé en debug.
LANGUAGE_POLICY_VERSION = "runtime_auto_v116_no_forced_french"
LANGUAGE_POLICY_VERSION_LINE = (
    "LANGUAGE_POLICY_VERSION: runtime_auto_v116_no_forced_french"
)

# Renfort LLM si le modèle produit une excuse « français uniquement » (ne pas persister cette variante).
_EN_VIOLATION_RETRY_SYSTEM_SUFFIX = (
    "\n\nCRITICAL LANGUAGE_ENFORCEMENT: The user's last message is in English. "
    "You MUST answer entirely in English. Never claim you can only express yourself in French. "
    "Never cite strict rules requiring French only."
)


def read_deployed_commit() -> str | None:
    for key in (
        "RAILWAY_GIT_COMMIT_SHA",
        "RAILWAY_GIT_COMMIT_FULL",
        "GIT_COMMIT_SHA",
        "VERCEL_GIT_COMMIT_SHA",
    ):
        v = (os.getenv(key) or "").strip()
        if v:
            return v[:48]
    return None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    profile: str = ""
    provider: str = ""
    project_name: str = Field("", validation_alias=AliasChoices("project_name", "project"))
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
        "You are OpenChawn, an AI orchestration system created by Robert. "
        "Follow the OUTPUT LANGUAGE / language block at the start of the user message when present. "
        "Keep answers concise. Never mention model providers or engine names.\n\n"
        f"{OPENCHAWN_RUNTIME_LANGUAGE_POLICY_EN}\n\n"
        f"{LANGUAGE_POLICY_VERSION_LINE}"
    )


def assemble_chat_generation_inputs(
    req: ChatRequest,
    *,
    user: dict,
    persist_memory_side_effects: bool = True,
    language_trace: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Assemble prompts pour un tour de chat.

    Ordre appliqué (alignement prod engineer V11.6) :
      2) Politique de langue (méta sans mémoire) + bloc OUTPUT LANGUAGE dans le futur prompt user ;
      3) Retrieval mémoire fractale ;
      4) Garde-langue runtime (sanitize) avant envoi gateway.
    """
    lt = language_trace or derive_response_language_trace(req.message)
    proj_hint = (req.project_name or "").strip()
    if user.get("is_guest"):
        user_key = f"guest-{(user.get('guest_session_id') or '')[:28]}"
    else:
        user_key = f"user-{user.get('id', '')}"

    profile_id = resolve_profile_id(req, user)
    profile = get_profile(profile_id)
    profile_prompt = str(profile.get("system_prompt") or "").strip()

    detected_lang_surface = lt["detected_language"]
    final_language = lt["final_language"]
    response_language_mode = lt["response_language_mode"]
    language_source = lt["language_source"]

    # Phase 2 — language policy applied to outbound instruction (sans état mémoire).
    lang_instruction = build_language_instruction(req.message)

    # Phase 3 — memory retrieval (+ effets annexes légers hors réponse brute).
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
        final_prompt = f"{memory_context}\n\n── USER REQUEST ──\n{base_request}"
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

    layered_user_message = f"{lang_instruction}\n\n{final_prompt}"

    base_system = build_openchawn_base_system_prompt()
    runtime_rules = build_runtime_rules_prompt()
    if runtime_rules:
        base_system = f"{base_system}\n\nRuntimeRules:\n{runtime_rules}"

    system_prompt = f"{profile_prompt}\n\n{base_system}" if profile_prompt else base_system

    pre_combined_scan = (system_prompt + "\n" + layered_user_message).strip()
    forced_french_runtime_detected = bool(prompt_contains_forced_french(pre_combined_scan))
    memory_ff = bool(prompt_contains_forced_french(memory_context or ""))
    profile_ff = bool(prompt_contains_forced_french(profile_prompt or ""))

    # Phase 4 — runtime guard (nettoyage lignes française forcée) avant gateway.
    sp_san, um_san, forced_french_runtime_removed = sanitize_provider_prompts(
        system_prompt, layered_user_message
    )
    provider_scan = (sp_san + "\n" + um_san).strip()
    provider_prompt_contains_forced_french = bool(prompt_contains_forced_french(provider_scan))

    return {
        "user_key": user_key,
        "profile_used": profile_id,
        "profile_prompt": profile_prompt,
        "memory_used": memory_used,
        "memory_count": len(memories),
        "memory_context_plain": memory_context,
        "detected_language": detected_lang_surface,
        "final_language_hint": final_language,
        "response_language_mode": response_language_mode,
        "language_source": language_source,
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
        "memory_contains_forced_french": memory_ff,
        "profile_contains_forced_french": profile_ff,
        "system_core_contains_forced_french": bool(prompt_contains_forced_french(base_system)),
        "provider_prompt_contains_forced_french": provider_prompt_contains_forced_french,
    }


def handle_chat_request(
    req: ChatRequest,
    user: dict,
    *,
    debug: bool,
    http_mount_path: str,
) -> dict[str, Any]:
    """
    Handler HTTP-agnostique commun à ``POST /chat`` et ``POST /api/chat``.

    Étapes garanties dans cette fonction ou ``assemble_chat_generation_inputs`` pour l'amont :
      1) quota / auth (guest) ;
      2–4) assemble : langue → mémoire → garde ;
      5) appel provider ;
      6) régénération violation langue EN ;
      7) persistence mémoire **uniquement** sur réponse finale valide et HTTP 200.
    """
    is_guest = user.get("is_guest", False)
    violation_retry = False
    quota: dict[str, Any] = {}

    # ── Phase 1: quota / auth ──
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

    trace = derive_response_language_trace(req.message)
    bundle = assemble_chat_generation_inputs(
        req, user=user, persist_memory_side_effects=True, language_trace=trace
    )
    provider_hint = (req.provider or "").strip().lower()

    ff_detected_bundle = bool(bundle.get("forced_french_runtime_detected"))
    ff_removed_assemble = bool(bundle.get("forced_french_runtime_removed_preview"))

    sp_in = bundle["sanitized_system_prompt"]
    um_in = bundle["sanitized_user_message"]
    route_signature = (
        ROUTE_SIGNATURE_POST_CHAT if http_mount_path == "/chat" else ROUTE_SIGNATURE_POST_API_CHAT
    )

    # ── Phase 5: provider ──
    response_language_violation_detected = False
    violation_on_first_generation = False

    llm_result = generate_response(
        system_prompt=sp_in,
        user_message=um_in,
        provider_hint=provider_hint,
    )
    response_text = llm_result.get("output", "")
    provider_used = llm_result.get("provider", "fallback")
    success = bool(llm_result.get("success", bool(response_text)))
    provider_error = llm_result.get("error", None)
    provider_status = llm_result.get("status_code", None)
    ff_removed_gateway = bool(llm_result.get("forced_french_runtime_removed", False))
    pre_ff = bool(llm_result.get("prompt_contains_forced_french_before_sanitize", False))

    # ── Phase 6: post-generation language violation ──
    if (
        success
        and response_text
        and detect_user_language(req.message) == "en"
        and assistant_reply_violates_english_user_expectation(response_text)
    ):
        violation_on_first_generation = True
        violation_retry = True
        logger.warning("language_policy_violation: regenerating with English enforcement (first reply discarded)")
        llm_result = generate_response(
            system_prompt=sp_in + _EN_VIOLATION_RETRY_SYSTEM_SUFFIX,
            user_message=um_in,
            provider_hint=provider_hint,
        )
        response_text = llm_result.get("output", "") or ""
        provider_used = llm_result.get("provider", provider_used)
        success = bool(llm_result.get("success", bool(response_text)))
        provider_error = llm_result.get("error", None)
        provider_status = llm_result.get("status_code", None)
        ff_removed_gateway = ff_removed_gateway or bool(llm_result.get("forced_french_runtime_removed", False))
        pre_ff = pre_ff or bool(llm_result.get("prompt_contains_forced_french_before_sanitize", False))

    if detect_user_language(req.message) == "en" and response_text:
        response_language_violation_detected = violation_on_first_generation or bool(
            assistant_reply_violates_english_user_expectation(response_text)
        )

    ff_removed_combined = ff_removed_assemble or ff_removed_gateway
    detected = str(bundle.get("detected_language") or "")
    final_lang = str(bundle.get("final_language_hint") or "")

    logger.info(
        "chat_route_trace "
        f"path={http_mount_path} handler={CHAT_HANDLER_NAME} tag={CHAT_PIPELINE_TAG} "
        f"mode={bundle.get('response_language_mode')} language_source={bundle.get('language_source')} "
        f"detected_language={detected} final_language={final_lang} "
        f"ff_detected={ff_detected_bundle} ff_removed_assemble={ff_removed_assemble} ff_removed_gateway={ff_removed_gateway} "
        f"debug={debug} provider={provider_used} success={success} "
        f"status={provider_status} guest={is_guest} "
        f"forced_french_before_gateway={pre_ff} en_violation_retry={violation_retry}"
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

    # ── Phase 7: memory writeback (après réponse finale valide uniquement) ──
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
        "route_signature": route_signature,
    }
    if is_guest:
        result["guest"] = True
        result["quota_remaining"] = quota["remaining"]
    deployed = read_deployed_commit()
    if debug:
        dbg: dict[str, Any] = {
            "route_signature": route_signature,
            "handler_name": CHAT_HANDLER_NAME,
            "provider_used": str(provider_used or ""),
            "profile_used": bundle["profile_used"],
            "detected_language": bundle["detected_language"],
            "final_language": bundle["final_language_hint"],
            "language_policy_version": LANGUAGE_POLICY_VERSION,
            "prompt_contains_forced_french": bool(bundle.get("prompt_contains_forced_french")),
            "memory_contains_forced_french": bool(bundle.get("memory_contains_forced_french")),
            "profile_contains_forced_french": bool(bundle.get("profile_contains_forced_french")),
            "provider_prompt_contains_forced_french": bool(bundle.get("provider_prompt_contains_forced_french")),
            "response_language_violation_detected": response_language_violation_detected,
            "route_used": f"POST {http_mount_path}",
            "response_language_mode": bundle["response_language_mode"],
            "language_source": bundle["language_source"],
            "forced_french_runtime_detected": ff_detected_bundle,
            "forced_french_runtime_removed": ff_removed_combined,
            "english_violation_regenerated": violation_retry,
        }
        if deployed:
            dbg["deployed_commit"] = deployed
        result.update(dbg)
    return result


@router.post("/chat")
def route_post_chat(
    req: ChatRequest,
    user: dict = Depends(get_current_user_or_guest),
    debug: bool = Query(default=False),
):
    """Entrée principale utilisée par ``static/index.html``."""
    return handle_chat_request(req, user, debug=debug, http_mount_path="/chat")


@router.post("/api/chat")
def route_post_api_chat(
    req: ChatRequest,
    user: dict = Depends(get_current_user_or_guest),
    debug: bool = Query(default=False),
):
    """Alias HTTP : même ``handle_chat_request`` que ``/chat``."""
    return handle_chat_request(req, user, debug=debug, http_mount_path="/api/chat")


# Export explicite pour tests / introspection instrumentation.
SHARED_CHAT_HANDLER = handle_chat_request
