from fastapi import FastAPI
from pydantic import BaseModel

from app.memory import save_memory, load_recent_memories

app = FastAPI()

class AskRequest(BaseModel):
    prompt: str

@app.get("/")
def root():
    return {"message": "OpenChawn is alive"}

@app.post("/ask")
def ask(request: AskRequest):
    save_memory("user", request.prompt)

    response = orchestrator(request.prompt)

    save_memory("openchawn", f"Réponse donnée au prompt: {request.prompt}")

    return {
        "response": response,
        "status": "ok"
    }


def orchestrator(prompt: str):
    memories = load_recent_memories(limit=6)

    memory_text = " | ".join(
        [f"{m['role']}: {m['content']}" for m in memories]
    )

    return (
        f"Processed locally: {prompt}\n"
        f"Recent memory: {memory_text}"
    )
