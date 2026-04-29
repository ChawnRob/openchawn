from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.orchestrator import handle
from app.mempalace import load_memories

router = APIRouter(prefix="/openchawn", tags=["openchawn"])


# ─── Schémas pydantic stricts ─────────────────────────────────────────────
class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    project: str = Field(default="openchawn", max_length=64)
    user_id: str = Field(default="robert", max_length=64)
    system_prompt: str = Field(default="", max_length=4000)


class HumanLayer(BaseModel):
    detected_emotion: str
    intent_hidden: str
    confidence_level: float
    recommended_nudge: str
    nudge_type: str


class ASIDecision(BaseModel):
    decision: str
    reason: str
    confidence: float
    memory_query: Optional[dict] = None
    memory_update: Optional[dict] = None
    model_routing: Optional[dict] = None
    human_layer: HumanLayer
    system_note: Optional[str] = None


class ChatResponse(BaseModel):
    action: str
    asi: ASIDecision
    output: Any
    provider: Optional[str] = None
    providers_tried: list[str] = []
    learned_memory_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    mempalace_entries: int
    version: str


# ─── Endpoints ────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        result = handle(
            req.prompt,
            project=req.project,
            user_id=req.user_id,
            system_prompt=req.system_prompt,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenChawn failure: {e}")
    return ChatResponse(**result)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        mempalace_entries=len(load_memories()),
        version="openchawn-0.1",
    )
