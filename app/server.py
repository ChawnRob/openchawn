"""
OpenChawn standalone FastAPI server.

Lance le pipeline ASI-Evolve via POST /ask sans dépendre du legacy main.py.
Usage:
    uvicorn app.server:app --reload --port 8000
"""
from __future__ import annotations
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.ask import router as ask_router
from routers.memory import router as memory_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

app = FastAPI(
    title="OpenChawn",
    version="1.0.0",
    description="Orchestrateur local-first explicable (MemPalace + ASI-evolve + Kimi + Minimax + Mistral + Ollama).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(ask_router)
app.include_router(memory_router)


@app.get("/")
def root():
    return {
        "service": "openchawn",
        "version": app.version,
        "endpoints": ["POST /ask", "GET /health"],
    }
