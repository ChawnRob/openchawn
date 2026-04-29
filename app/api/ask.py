from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.orchestrator import ask as orchestrator_ask

router = APIRouter(tags=["openchawn"])


class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    project: str = Field(default="default", max_length=64)
    user_id: str = Field(default="Robert1982", max_length=64)


class TraceStep(BaseModel):
    source_module: str
    action: str
    reason: str
    input_summary: str
    output_summary: str
    confidence: float


class AskResponse(BaseModel):
    answer: str
    confidence: float
    retried: bool
    trace: List[TraceStep]


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest) -> AskResponse:
    try:
        result = orchestrator_ask(
            prompt=req.prompt,
            project=req.project,
            user_id=req.user_id,
        )
        return AskResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"orchestrator error: {e.__class__.__name__}: {e}")


@router.get("/health")
def health():
    return {"status": "ok", "service": "openchawn"}
