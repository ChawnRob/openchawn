import logging
import os
import re
import requests as http_requests
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, field_validator
from app.config import (
    ALLOWED_ORIGINS,
    IS_PROD,
    LOG_LEVEL,
    MAX_MESSAGE_LENGTH,
    MODEL_PROVIDER,
)
from app.provider_manager import get_provider_manager
from app.settings import get_settings
from app.profiles import list_profiles, get_profile_for_user
from app.auth.database import init_db, create_user, get_user_by_email, update_user_business
from app.auth.security import hash_password, verify_password, create_token
from app.auth.deps import get_current_user
from app.auth.guest import create_guest_session, get_guest_quota_status
from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware, global_error_handler
from app.api.chat import router as chat_router


logging.basicConfig(
    level=getattr(logging, (LOG_LEVEL or "INFO").upper(), logging.INFO),
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
app.include_router(chat_router)


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


class ProviderTestRequest(BaseModel):
    provider: str
    message: str



@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    return Response(status_code=204)


@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon_precomposed():
    return Response(status_code=204)



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



@app.get("/health")
def health():
    return {"mode": "handle", "status": "ok"}


@app.get("/health/providers")
def health_providers():
    """État des providers LLM (Railway / ops) — sans secrets."""
    pm = get_provider_manager()
    s = get_settings()
    return {
        "environment": s.openchawn_env,
        "default_provider": (s.default_provider or "") or None,
        "active_provider": pm.active_provider() or None,
        "available_providers": pm.available_providers(),
        "missing_required_keys": pm.missing_required_keys(),
        "ollama_enabled": s.ollama_enabled,
        "production_safe": pm.production_safe(),
    }



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


@app.post("/chat-test")
def chat_test(req: ChatTestRequest):
    """Appelle Ollama directement, sans auth. Debug uniquement."""
    s = get_settings()
    if not s.ollama_enabled:
        raise HTTPException(
            status_code=403,
            detail="Ollama désactivé (OLLAMA_ENABLED=false). Activez Ollama et définissez OLLAMA_URL.",
        )
    base = (s.ollama_base_url or s.ollama_url or "").strip().rstrip("/")
    if not base:
        raise HTTPException(
            status_code=503,
            detail="OLLAMA_URL / OLLAMA_BASE_URL manquant alors qu'Ollama est activé.",
        )
    gen_url = f"{base}/api/generate"
    try:
        r = http_requests.post(
            gen_url,
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


# ── Providers diagnostic (protégé) ──────────────────────

@app.get("/providers/status")
def providers_status(user: dict = Depends(get_current_user)):
    _ = user
    return {
        "model_provider": MODEL_PROVIDER or "auto",
        "openrouter_api_key_present": bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
        "openrouter_model_present": bool((os.getenv("OPENROUTER_MODEL") or "").strip()),
        "euria_api_key_present": bool((os.getenv("EURIA_API_KEY") or "").strip()),
        "euria_provider_present": bool((os.getenv("EURIA_PROVIDER") or "").strip()),
    }


@app.post("/providers/test")
def providers_test(req: ProviderTestRequest, user: dict = Depends(get_current_user)):
    _ = user
    provider = (req.provider or "").strip().lower()
    logger.info(f"provider test requested | provider={provider}")

    if provider == "openrouter":
        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        base_url = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
        model = (os.getenv("OPENROUTER_MODEL") or "openrouter/auto").strip()

        if not api_key:
            logger.warning("provider test openrouter | missing key")
            return {
                "provider": "openrouter",
                "model": model,
                "success": False,
                "status_code": None,
                "response_preview": "",
                "error": "OPENROUTER_API_KEY_MISSING",
            }

        try:
            r = http_requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": req.message},
                    ],
                    "stream": False,
                },
                timeout=30,
            )
            status_code = r.status_code
            body_preview = (r.text or "")[:240]
            logger.info(f"provider test openrouter | response status={status_code}")

            if not r.ok:
                logger.warning(f"provider test openrouter | error body={body_preview}")
                return {
                    "provider": "openrouter",
                    "model": model,
                    "success": False,
                    "status_code": status_code,
                    "response_preview": "",
                    "error": body_preview or "OPENROUTER_REQUEST_FAILED",
                }

            data = r.json()
            output = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return {
                "provider": "openrouter",
                "model": model,
                "success": True,
                "status_code": status_code,
                "response_preview": str(output)[:240],
                "error": None,
            }
        except Exception as e:
            logger.warning(f"provider test openrouter | exception={e.__class__.__name__}: {e}")
            return {
                "provider": "openrouter",
                "model": model,
                "success": False,
                "status_code": None,
                "response_preview": "",
                "error": f"{e.__class__.__name__}: {e}",
            }

    if provider == "euria":
        logger.warning("provider test euria | EURIA endpoint not configured")
        return {
            "provider": "euria",
            "model": None,
            "success": False,
            "status_code": None,
            "response_preview": "",
            "error": "EURIA_ENDPOINT_NOT_CONFIGURED",
        }

    return {
        "provider": provider or None,
        "model": None,
        "success": False,
        "status_code": None,
        "response_preview": "",
        "error": "UNSUPPORTED_PROVIDER",
    }


# ── Guest mode ──────────────────────────────────────────

@app.post("/guest/session")
def guest_session(request: Request):
    """Crée une session guest anonyme. Aucun login requis."""
    client_ip = request.client.host if request.client else "unknown"
    session = create_guest_session(client_ip)
    return session


@app.get("/guest/quota")
def guest_quota(request: Request):
    """Vérifie le quota restant d'une session guest."""
    session_id = request.headers.get("X-Guest-Session", "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Header X-Guest-Session manquant")
    status = get_guest_quota_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="Session guest inconnue")
    return status


# ── Static files ─────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")
