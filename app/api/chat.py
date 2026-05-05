from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

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
            raise HTTPException(
                status_code=429,
                detail=(
                    "Vous avez utilisé vos 5 messages gratuits aujourd'hui. "
                    "Créez un compte pour continuer."
                ),
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

    system_prompt = (
        "Tu es OpenChawn, un système d'orchestration d'intelligence artificielle créé par Robert. "
        "RÈGLES STRICTES : "
        "1. Réponds UNIQUEMENT en français. Jamais de chinois, anglais ou autre langue. "
        "2. Réponds brièvement et directement. "
        "3. Ne mentionne jamais Mistral, OpenAI, Qwen ou un autre provider. "
        "4. Tu es OpenChawn, point final."
    )

    llm_result = generate_response(
        system_prompt=system_prompt,
        user_message=final_prompt,
    )
    response_text = llm_result.get("output", "")
    provider_used = llm_result.get("provider", "fallback")

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
    return result
