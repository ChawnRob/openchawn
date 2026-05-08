import logging
import os
import re
import requests as http_requests
from fastapi import FastAPI, Request, HTTPException, Depends, Query
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
from app.profiles import list_profiles, get_profile_for_user
from app.routing import get_cost_tracking_hooks, get_fallback_manager, get_provider_health_hooks
from app.memory.fractal_memory import (
    concept_graph_lightweight,
    concept_memories,
    get_last_memory_context,
    list_archived_memories,
    memories_by_type,
    memory_health,
    memory_lifecycle_health,
    memory_observability_overview,
    memory_trace,
    recent_memories,
    search_memories,
    store_indexes_snapshot,
    top_memories,
)
from app.memory import memory_timeline as mem_timeline
from app.memory import memory_index as mem_index
from app.memory import memory_decision_engine as mem_decision
from app.memory import memory_reflection_engine as mem_reflect
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


class PredictConsequencesRequest(BaseModel):
    proposed_action: str
    project: str = "openchawn"

    @field_validator("proposed_action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        s = (v or "").strip()
        if len(s) < 2:
            raise ValueError("proposed_action trop court")
        return s[:8000]


class ProviderTestRequest(BaseModel):
    provider: str
    message: str


class MemorySearchRequest(BaseModel):
    query: str


class MemoryCompressionRunRequest(BaseModel):
    dry_run: bool = False
    include_archived: bool = False
    project: str = ""


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
    health = get_provider_health_hooks()
    cost = get_cost_tracking_hooks()
    fallback = get_fallback_manager()
    return {
        "active_provider": pm.active_provider() or None,
        "configured_providers": pm.configured_providers(),
        "missing_keys": pm.missing_keys(),
        "production_safe": pm.production_safe(),
        "capabilities": pm.capabilities_snapshot(),
        "provider_health": health.snapshot(),
        "cost_tracking": cost.snapshot(),
        "fallback_recent": [
            {"provider": ev.provider, "reason": ev.reason, "timestamp": ev.timestamp}
            for ev in fallback.recent(limit=10)
        ],
    }


@app.get("/health/security")
def health_security():
    """
    Endpoint de sécurité (future-ready) : ne retourne jamais de secret brut.
    """
    tracked_env_safe = True
    # .env est ignoré mais peut exister localement (normal en dev)
    env_file_present = os.path.isfile(".env")
    files_at_risk: list[str] = []
    compromised_keys_possible = False
    secrets_found: list[str] = []

    # Signaux de risque connus (patterns historiques non prod)
    if os.path.isfile("tests/test_learn.py"):
        files_at_risk.append("tests/test_learn.py")
        compromised_keys_possible = True
        secrets_found.append("secret_like_pattern_in_test_fixture")
    if os.path.isfile("app/router"):
        files_at_risk.append("app/router")
        compromised_keys_possible = True
        secrets_found.append("secret_like_pattern_in_legacy_file")

    # ENV safe = fichier .env local autorisé, tant qu'il n'est pas tracké.
    env_safe = tracked_env_safe
    if env_file_present:
        secrets_found.append("local_env_file_present_untracked_expected")

    return {
        "secrets_found": sorted(set(secrets_found)),
        "git_safe": not compromised_keys_possible,
        "env_safe": env_safe,
        "compromised_keys_possible": compromised_keys_possible,
        "files_at_risk": sorted(set(files_at_risk)),
    }


@app.get("/health/memory")
def health_memory():
    return memory_health()


@app.get("/health/memory/lifecycle")
def health_memory_lifecycle():
    return memory_lifecycle_health()


@app.get("/health/language")
def health_language():
    from app.core import language_policy as lp

    return {
        "language_policy_enabled": lp.LANGUAGE_POLICY_ENABLED,
        "fallback_language": lp.FALLBACK_LANGUAGE,
        "rule": lp.LANGUAGE_POLICY_RULE_PUBLIC,
    }


@app.get("/memory/recent")
def memory_recent():
    items = recent_memories(limit=10)
    return {"status": "ok", "count": len(items), "items": items}


@app.post("/memory/search")
def memory_search(req: MemorySearchRequest):
    items = search_memories(req.query, limit=10)
    return {"status": "ok", "count": len(items), "items": items}


@app.get("/memory/concepts")
def memory_concepts():
    items = concept_memories(limit=20)
    return {"status": "ok", "count": len(items), "items": items}


@app.get("/memory/top")
def memory_top():
    items = top_memories(limit=10)
    return {"status": "ok", "count": len(items), "items": items}


@app.get("/memory/system")
def memory_system():
    idx = store_indexes_snapshot()
    return {
        "status": "ok",
        "indexes": idx.get("system_concepts"),
        "entries": memories_by_type("system", 80, include_archived=True),
    }


@app.get("/memory/projects")
def memory_projects_view():
    idx = store_indexes_snapshot()
    return {
        "status": "ok",
        "indexes": idx.get("project_concepts"),
        "entries": memories_by_type("project", 120, include_archived=True),
    }


@app.get("/memory/user")
def memory_user_view():
    idx = store_indexes_snapshot()
    return {
        "status": "ok",
        "indexes": idx.get("user_preferences"),
        "entries": memories_by_type("user", 120, include_archived=True),
    }


@app.get("/memory/session")
def memory_session_view():
    return {
        "status": "ok",
        "indexes": [],
        "entries": memories_by_type("session", 100, include_archived=True),
    }


@app.get("/memory/observability/overview")
def memory_observability_overview_route():
    return memory_observability_overview()


@app.get("/memory/trace/{memory_id}")
def memory_trace_route(memory_id: str):
    out = memory_trace(memory_id)
    if out.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Mémoire introuvable")
    return out


@app.get("/memory/last-context")
def memory_last_context():
    return get_last_memory_context()


@app.get("/memory/concepts/graph")
def memory_concepts_graph():
    return concept_graph_lightweight()


@app.get("/memory/archive")
def memory_archive_route(
    project: str = Query(default=""),
    memory_type: str = Query(default=""),
    older_than_days: float | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=150),
):
    return list_archived_memories(
        project=project,
        memory_type=memory_type,
        older_than_days=older_than_days,
        limit=limit,
    )


@app.get("/memory/timeline")
def memory_timeline_route(
    project: str = Query(default=""),
    memory_type: str = Query(default=""),
    event_type: str = Query(default=""),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
):
    events = mem_timeline.filter_timeline_events(
        project=project,
        memory_type=memory_type,
        event_type=event_type,
        since=since,
        until=until,
        limit=limit,
    )
    return {"status": "ok", "count": len(events), "events": events}


@app.get("/memory/replay")
def memory_replay_route(
    project: str = Query(default=""),
    memory_type: str = Query(default=""),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    limit: int = Query(default=250, ge=1, le=500),
):
    return mem_timeline.build_replay_payload(
        project=project,
        memory_type=memory_type,
        since=since,
        until=until,
        limit=limit,
    )


@app.get("/memory/replay/session/{session_id}")
def memory_replay_session_route(session_id: str, limit: int = Query(default=200, ge=1, le=500)):
    return mem_timeline.build_session_replay(session_id, limit=limit)


@app.get("/memory/decision-trace")
def memory_decision_trace_route(
    concept: str = Query(..., min_length=1),
    project: str = Query(default=""),
):
    return mem_timeline.decision_trace(concept=concept, project=project)


@app.get("/memory/index")
def memory_index_route():
    return mem_index.build_memory_index()


@app.get("/memory/concepts/top")
def memory_concepts_top_route(limit: int = Query(default=12, ge=1, le=80)):
    return mem_index.top_concepts_response(limit)


@app.get("/memory/graph/stats")
def memory_graph_stats_route():
    return mem_index.graph_statistics()


@app.get("/memory/projects/gravity")
def memory_projects_gravity_route():
    return mem_index.projects_gravity_board()


@app.get("/memory/decision/last")
def memory_decision_last_route():
    return mem_decision.lean_decision_payload(mem_decision.get_last_decision_bundle())


@app.get("/memory/decision/simulate")
def memory_decision_simulate_route(
    query: str = Query(..., min_length=1),
    project: str = Query(default=""),
    user_key: str = Query(default=""),
    as_guest: bool = Query(default=True),
):
    bundle = mem_decision.simulate_memory_decision(
        query=query,
        project=project,
        user_key=user_key,
        is_guest=as_guest,
    )
    lean = mem_decision.lean_decision_payload(bundle)
    return {
        "status": "ok",
        "simulate": True,
        "candidate_count": bundle.get("candidate_count"),
        "selected": lean.get("selected_memories"),
        "rejected": lean.get("rejected_memories"),
        "scoring_breakdown": bundle.get("scoring_breakdown"),
        "conflicts_detected": bundle.get("conflicts_detected"),
        "final_context_preview": lean.get("final_context_preview"),
        "confidence_hint": bundle.get("confidence_hint"),
        "arbitration_summary": bundle.get("arbitration_summary"),
    }


@app.get("/memory/reflection/report")
def memory_reflection_report_route():
    return mem_reflect.build_reflection_report()


@app.get("/memory/retrieval-policy")
def memory_retrieval_policy_route():
    from app.memory import retrieval_policy as rp

    last = rp.get_last_retrieval_policy()
    if last.get("status") == "ok":
        return rp.lean_policy_response(last)
    return rp.lean_policy_response(rp.build_retrieval_policy())


@app.get("/memory/retrieval-policy/simulate")
def memory_retrieval_policy_simulate_route(state: str = Query(default="stable")):
    from app.memory import retrieval_policy as rp

    return rp.simulate_policy_for_state(state)


@app.get("/memory/compression/candidates")
def memory_compression_candidates_route(include_archived: bool = Query(default=False)):
    from app.memory import memory_compression as mc
    from app.memory.fractal_memory import entries_snapshot_for_tests

    return mc.find_compression_candidates(entries_snapshot_for_tests(), include_archived=include_archived)


@app.post("/memory/compression/run")
def memory_compression_run_route(req: MemoryCompressionRunRequest):
    from app.memory import memory_compression as mc

    proj = str(req.project or "").strip()
    return mc.run_memory_compression_job(
        include_archived=bool(req.include_archived),
        dry_run=bool(req.dry_run),
        project=(proj if proj else None),
    )


@app.get("/memory/compression/health")
def memory_compression_health_route():
    from app.memory import memory_compression as mc

    return mc.compression_health_report()


@app.get("/memory/compression/{compressed_id}")
def memory_compression_get_route(compressed_id: str):
    from app.memory import memory_compression as mc

    out = mc.get_compressed_memory_by_id(compressed_id)
    if str(out.get("detail") or "") == "not_compressed_type":
        raise HTTPException(status_code=400, detail="Ce n’est pas une entrée mémoire de type compressed")
    if str(out.get("status") or "") != "ok":
        raise HTTPException(status_code=404, detail="Mémoire introuvable")
    return out


@app.get("/memory/consolidation/plan")
def memory_consolidation_plan_route():
    from app.memory import memory_consolidation_scheduler as mcs

    return mcs.build_consolidation_plan()


@app.post("/memory/consolidation/run-light")
def memory_consolidation_run_light_route():
    from app.memory import memory_consolidation_scheduler as mcs

    return mcs.run_light_consolidation()


@app.post("/memory/consolidation/run-deep")
def memory_consolidation_run_deep_route():
    from app.memory import memory_consolidation_scheduler as mcs

    return mcs.run_deep_consolidation()


@app.get("/memory/consolidation/last-report")
def memory_consolidation_last_report_route():
    from app.memory import memory_consolidation_scheduler as mcs

    return mcs.get_last_consolidation_report()


@app.post("/decision/predict-consequences")
def decision_predict_consequences_route(req: PredictConsequencesRequest):
    from app.decision import consequence_predictor as cp

    dc = mem_decision.get_last_decision_bundle()
    return cp.build_impact_report(
        proposed_action=req.proposed_action,
        project=(req.project or "").strip(),
        related_memories=[],
        decision_context=dc,
    )


@app.get("/decision/last-impact")
def decision_last_impact_route():
    from app.decision import consequence_predictor as cp

    rep = cp.get_last_impact_report()
    if (rep.get("status") or "") == "empty":
        return {
            "status": "empty",
            "likely_benefits": [],
            "likely_risks": [],
            "technical_impact": "",
            "cost_impact": "",
            "stability_impact": "",
            "security_impact": "",
            "provider_impact": "",
            "memory_impact": "",
            "confidence_hint": None,
        }
    return rep


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
    """Conservé pour compat URL ; plus d’appel local Ollama (route désactivée)."""
    raise HTTPException(
        status_code=410,
        detail="OpenChawn n'utilise plus Ollama (/chat avec providers cloud uniquement).",
    )


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
