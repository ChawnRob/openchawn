<<<<<<< HEAD
import logging
import re
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

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO if IS_PROD else logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("openchawn")

# ── App ──────────────────────────────────────────────────
app = FastAPI(
    title="OpenChawn",
    version="0.6.0",
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)

# ── Middlewares (ordre = dernier ajouté s'exécute en premier) ──
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)

# ── Error handler global ─────────────────────────────────
app.add_exception_handler(Exception, global_error_handler)

# ── Init ─────────────────────────────────────────────────
init_db()
model_router = handle

# ── Validation email ─────────────────────────────────────
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


# ── Modèles ──────────────────────────────────────────────

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


# ── Frontend ─────────────────────────────────────────────
@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")


# ── Auth : Register ──────────────────────────────────────
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


# ── Auth : Login ─────────────────────────────────────────
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


# ── Chat (protégé) ───────────────────────────────────────
@app.post("/chat")
def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    from memory.fractal_memory import search_nodes, add_node

    # 🔹 mémoire
    memories = search_nodes(req.message)

    context = ""
    if memories:
        context = "\n".join([str(m.get("content", "")) for m in memories[:3]])

    # prompt final — le system prompt concis est injecté dans router.py
    if context:
        final_prompt = f"Contexte mémoire:\n{context}\n\n{req.message}"
    else:
        final_prompt = req.message

    # 🔹 appel modèle
    
    raw_response = model_router(final_prompt)
    print("DEBUG RAW_RESPONSE:", raw_response)
    if isinstance(raw_response,dict) and raw_response.get("action") == "MEMORY_READ":
        raw_response = None
    

    # 🔹 parsing SAFE
    if isinstance(raw_response, dict):
        response_text = (
            raw_response.get("output")
            or raw_response.get("response")
            or raw_response.get("message")
            or str(raw_response)
        )
    else:
        response_text = str(raw_response)

    # 🔹 fallback
    if (
         not response_text
         or response_text.strip() in ["", "[]", "{}", "None"]
         or response_text.strip() == req.message.strip()
    ):
         response_text = "Je suis OpenChawn. Comment puis-je t’aider ?"
    # 🔹 mémoire
    add_node(content=req.message, tags=["user"], source="chat")
    add_node(content=response_text, tags=["assistant"], source="chat")

    return {"output": response_text}


# ── Health (public) ──────────────────────────────────────
@app.get("/health")
def health():
    status = {"mode": "handle", "status": "ok"}
    # Ne pas exposer les détails internes en prod
    if IS_PROD:
        return {
            "status": "ok" if status.get("providers") else "degraded",
            "providers": [
                {"name": p["name"], "available": p["available"]}
                for p in status.get("providers", [])
            ],
        }
    return status


# ── Profiles (public) ────────────────────────────────────
@app.get("/profiles")
def profiles():
    return list_profiles()


# ── History (protégé, propre user uniquement) ─────────────
@app.get("/history")
def history(limit: int = 20, user: dict = Depends(get_current_user)):
    user_id = f"user-{user['id']}"
    limit = min(limit, 100)  # cap
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


# ── Static files ─────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")
=======
"""
HALT / Food Radar — FastAPI entrypoint.

Run: uvicorn app.main:app --reload --port 8000
Open: http://localhost:8000
"""
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import engine, repository
from app.schemas import PlaceCard, PlaceDetail, Verdict, VerdictNamed

app = FastAPI(title="HALT / Food Radar", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/places", response_model=List[PlaceCard])
def list_places():
    out: List[PlaceCard] = []
    for p in repository.list_places():
        v = engine.compute_verdict(p)
        out.append(
            PlaceCard(
                id=p["id"],
                name=p["name"],
                cuisine=p["cuisine"],
                address=p["address"],
                district=p.get("district"),
                sector=p.get("sector"),
                lat=p["lat"],
                lng=p["lng"],
                verdict=v["verdict"],
                explanation=v["explanation"],
                sources=v["sources"],
            )
        )
    return out


@app.get("/places/{place_id}", response_model=PlaceDetail)
def get_place(place_id: str):
    p = repository.get_place(place_id)
    if not p:
        raise HTTPException(status_code=404, detail="Place not found")
    v = engine.compute_verdict(p)
    return PlaceDetail(
        id=p["id"],
        name=p["name"],
        cuisine=p["cuisine"],
        address=p["address"],
        district=p.get("district"),
        sector=p.get("sector"),
        lat=p["lat"],
        lng=p["lng"],
        verdict=Verdict(**v),
    )


@app.get("/verdict/{place_id}", response_model=VerdictNamed)
def get_verdict(place_id: str):
    p = repository.get_place(place_id)
    if not p:
        raise HTTPException(status_code=404, detail="Place not found")
    v = engine.compute_verdict(p)
    return VerdictNamed(name=p["name"], **v)


@app.get("/", response_class=HTMLResponse)
def index():
    html_path = _STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>HALT / Food Radar</h1><p>See /docs</p>")
>>>>>>> 3b574f3bedca39618e1e690171b52968536d0b88
