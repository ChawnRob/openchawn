from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.auth.deps import get_current_user_or_guest
from app.auth.guest import check_guest_quota
from app.config import MAX_MESSAGE_LENGTH
from app.llm import generate_response
from memory.fractal_memory import add_node, search_nodes

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


@router.post("/chat")
def chat(
    req: ChatRequest,
    user: dict = Depends(get_current_user_or_guest),
    debug: bool = Query(default=False),
):
    is_guest = user.get("is_guest", False)

    # ── Guest quota check ──
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

    # ── Memory (authenticated users only) ──
    context = ""
    memory_used = False
    if not is_guest:
        memories = search_nodes(req.message)
        if memories:
            context = "\n".join([str(m.get("content", "")) for m in memories[:3]])
            memory_used = True

    if context:
        final_prompt = f"Contexte mémoire:\n{context}\n\nQuestion: {req.message}"
    else:
        final_prompt = req.message

    # ── Enrich prompt with optional V11.6 fields ──
    extra_parts = []
    if req.project_name:
        extra_parts.append(f"Projet: {req.project_name}")
    if req.memory_context:
        extra_parts.append(f"Mémoire: {req.memory_context}")
    if req.user_goal:
        extra_parts.append(f"Objectif: {req.user_goal}")
    if extra_parts:
        final_prompt = "\n".join(extra_parts) + "\n\n" + final_prompt

    system_prompt = (
        "Tu es OpenChawn, un système d'orchestration d'intelligence artificielle créé par Robert. "
        "RÈGLES STRICTES : "
        "1. Réponds UNIQUEMENT en français. Jamais de chinois, anglais ou autre langue. "
        "2. Réponds brièvement et directement. "
        "3. Ne mentionne jamais Mistral, OpenAI, Qwen ou un autre provider. "
        "4. Tu es OpenChawn, point final."
    )

    provider_hint = (req.provider or "").strip().lower()

    llm_result = generate_response(
        system_prompt=system_prompt,
        user_message=final_prompt,
        provider_hint=provider_hint,
    )
    response_text = llm_result.get("output", "")
    provider_used = llm_result.get("provider", "fallback")
    success = bool(llm_result.get("success", bool(response_text)))
    provider_error = llm_result.get("error", None)
    provider_status = llm_result.get("status_code", None)

    logger.info(
        f"chat provider={provider_used} success={success} "
        f"status={provider_status} guest={is_guest}"
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

    # ── Memory persistence (authenticated users only) ──
    if not is_guest:
        add_node(content=req.message, tags=["user"], source="chat")
        add_node(content=response_text, tags=["assistant"], source="chat")

    result = {
        "output": response_text,
        "memory_used": memory_used,
    }
    if is_guest:
        result["guest"] = True
        result["quota_remaining"] = quota["remaining"]
    if debug:
        result["provider"] = provider_used
        result["provider_status"] = provider_status
    return result
