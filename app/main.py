import logging
import re
import requests as http_requests
from app.router import handle
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from app.config import ALLOWED_ORIGINS, IS_PROD, MAX_MESSAGE_LENGTH
from app.profiles import list_profiles, get_profile_for_user
from app.auth.database import init_db, create_user, get_user_by_email, update_user_business
from app.auth.security import hash_password, verify_password, create_token
from app.auth.deps import get_current_user
from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware, global_error_handler


logging.basicConfig(
    level=logging.INFO if IS_PROD else logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("openchawn")


app = FastAPI(
    title="OpenChawn",
    version="0.6.0",
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)


app.add_exception_handler(Exception, global_error_handler)


init_db()
model_router = handle


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")




class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""
    business_type: str = "default"

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Email invalide")
        if len(v) > 255:
            raise ValueError("Email trop long")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Mot de passe : minimum 8 caractères")
        if len(v) > 128:
            raise ValueError("Mot de passe trop long")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_name(cls, v):
        return v.strip()[:100]

    @field_validator("business_type")
    @classmethod
    def validate_business(cls, v):
        from app.profiles import PROFILES
        if v not in PROFILES:
            raise ValueError(f"Type métier inconnu: {v}")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return v.strip().lower()


class ChatRequest(BaseModel):
    message: str
    profile: str = ""

    @field_validator("message")
    @classmethod
    def validate_message(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Message vide")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message trop long ({MAX_MESSAGE_LENGTH} max)")
        return v


class UpdateBusinessRequest(BaseModel):
    business_type: str

    @field_validator("business_type")
    @classmethod
    def validate_business(cls, v):
        from app.profiles import PROFILES
        if v not in PROFILES:
            raise ValueError(f"Type métier inconnu: {v}")
        return v


class ChatTestRequest(BaseModel):
    message: str
    model: str = "mistral:7b"



@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")



@app.post("/register")
def register(req: RegisterRequest):
    pw_hash = hash_password(req.password)
    user = create_user(req.email, pw_hash, req.display_name, req.business_type)
    if not user:
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    token = create_token(user["id"], user["email"])
    logger.info(f"Nouveau user: {user['email']} ({user['business_type']})")
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "business_type": user["business_type"],
        },
    }



@app.post("/login")
def login(req: LoginRequest):
    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    token = create_token(user["id"], user["email"])
    logger.info(f"Login: {user['email']}")
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "business_type": user["business_type"],
        },
    }



@app.post("/chat")
def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    from memory.fractal_memory import search_nodes, add_node

    # mémoire
    memories = search_nodes(req.message)

    context = ""
    memory_used = False
    if memories:
        context = "\n".join([str(m.get("content", "")) for m in memories[:3]])
        memory_used = True

    # prompt final
    if context:
        final_prompt = f"Contexte mémoire:\n{context}\n\nQuestion: {req.message}"
    else:
        final_prompt = req.message

    # system prompt
    system_prompt = (
        "Tu es OpenChawn, un système d'orchestration d'intelligence artificielle créé par Robert. "
        "RÈGLES STRICTES : "
        "1. Réponds UNIQUEMENT en français. Jamais de chinois, anglais ou autre langue. "
        "2. Réponds brièvement et directement. "
        "3. Ne mentionne jamais Mistral, OpenAI, Qwen ou un autre provider. "
        "4. Tu es OpenChawn, point final."
    )

    # appel Ollama directement
    response_text = ""
    provider_used = "none"

    try:
        r = http_requests.post(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model": "mistral:7b",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": final_prompt},
                ],
                "stream": False,
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        response_text = data.get("message", {}).get("content", "")
        provider_used = "ollama/mistral:7b"
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")

    # fallback
    if not response_text or response_text.strip() in ["", "None"]:
        response_text = "Je suis OpenChawn. Aucun modèle n'a répondu."
        provider_used = "fallback"

    # sauvegarde mémoire
    add_node(content=req.message, tags=["user"], source="chat")
    add_node(content=response_text, tags=["assistant"], source="chat")

    return {
        "output": response_text,
        "provider": provider_used,
        "memory_used": memory_used,
    }



@app.get("/health")
def health():
    status = {"mode": "handle", "status": "ok"}
    if IS_PROD:
        return {
            "status": "ok" if status.get("providers") else "degraded",
            "providers": [
                {"name": p["name"], "available": p["available"]}
                for p in status.get("providers", [])
            ],
        }
    return status



@app.get("/profiles")
def profiles():
    return list_profiles()



@app.get("/history")
def history(limit: int = 20, user: dict = Depends(get_current_user)):
    user_id = f"user-{user['id']}"
    limit = min(limit, 100)
    return {"user_id": user_id, "history": router.get_history(user_id, limit)}


@app.delete("/history")
def clear_history(user: dict = Depends(get_current_user)):
    user_id = f"user-{user['id']}"
    router.clear_history(user_id)
    return {"status": "cleared"}


# ── QEI (protégé) ────────────────────────────────────────
@app.get("/qei/stats")
def qei_stats(user: dict = Depends(get_current_user)):
    return router.get_qei_stats()


@app.get("/qei/logs")
def qei_logs(user: dict = Depends(get_current_user)):
    return router.get_qei_logs()


# ── Memory ───────────────────────────────────────────────
from app.memory_loader import load_obsidian_memory

@app.get("/memory")
def memory():
    return load_obsidian_memory()


# ── Chat Test (NO AUTH — debug) ──────────────────────────
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


@app.post("/chat-test")
def chat_test(req: ChatTestRequest):
    """Appelle Ollama directement, sans auth. Debug uniquement."""
    try:
        r = http_requests.post(
            OLLAMA_URL,
            json={
                "model": req.model,
                "prompt": req.message,
                "stream": False,
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        return {
            "model": data.get("model", req.model),
            "response": data.get("response", ""),
            "memory_used": False,
        }
    except http_requests.ConnectionError:
        raise HTTPException(status_code=503, detail="Ollama non joignable sur :11434")
    except http_requests.Timeout:
        raise HTTPException(status_code=504, detail="Ollama timeout (120s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Static files ─────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")
