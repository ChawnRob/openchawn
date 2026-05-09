import logging
import os
import re
from datetime import datetime, timezone
import requests as http_requests
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from app.config import (
    ALLOWED_ORIGINS,
    IS_PROD,
    LOG_LEVEL,
    MAX_MESSAGE_LENGTH,
    MODEL_PROVIDER,
)
from app.provider_manager import get_provider_manager
from app.provider_runtime_config import INCIDENT_PROBE_PROVIDER_RUNTIME_REVISION
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

_APP_STARTED_AT = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


class MemoryContradictionResolveRequest(BaseModel):
    winner_memory_id: str
    loser_memory_id: str
    reason: str = ""
    mode: str = "manual"


class DecisionArbitrationOptionRequest(BaseModel):
    title: str
    source_memory_ids: list[str] = []
    option_id: str = ""
    strategy_type: str = ""


class DecisionArbitrationSimulateRequest(BaseModel):
    project: str = "openchawn"
    decision_type: str = "unknown"
    options: list[DecisionArbitrationOptionRequest]


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
    from app.core import initial_rules as ir
    from app.core import language_policy as lp

    audit = ir.load_initial_rules()
    return {
        "language_policy_enabled": lp.LANGUAGE_POLICY_ENABLED,
        "forced_french_rule_found": bool(audit.get("forced_french_rule_found")),
        "forced_french_rule_removed": bool(audit.get("forced_french_rule_removed")),
        "rule_sources_checked": list(audit.get("rule_sources_checked") or []),
        "fallback_language": lp.FALLBACK_LANGUAGE,
        "rule": lp.LANGUAGE_POLICY_RULE_PUBLIC,
        "priority": [
            "translation_target",
            "explicit_language_request",
            "latest_user_message_language",
            "fallback",
        ],
    }


@app.get("/health/provider-runtime")
def health_provider_runtime():
    """Diagnostic provider (V11.6) : booléens uniquement, jamais de secrets."""
    from app.provider_runtime_config import get_provider_runtime_config

    return get_provider_runtime_config()


def _incident_forced_french_line_snippets(blob: str, *, max_lines: int = 8) -> list[str]:
    from app.core.runtime_language_guard import line_contains_forced_french_pattern

    out: list[str] = []
    for line in (blob or "").splitlines():
        if not line_contains_forced_french_pattern(line):
            continue
        s = line.strip()
        if len(s) > 100:
            s = s[:97] + "…"
        out.append(s)
        if len(out) >= max_lines:
            break
    return out


@app.get("/__runtime", include_in_schema=False)
def incident_runtime_meta():
    """SRE V11.6 : identité process + version politique + commit déploiement."""
    from app.api.chat import LANGUAGE_POLICY_VERSION, read_deployed_commit

    env = (
        (os.getenv("OPENCHAWN_ENV") or "").strip()
        or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip()
        or "unknown"
    )
    return {
        "app": "OpenChawn",
        "version": str(getattr(app, "version", "") or "0.6.0"),
        "git_commit": read_deployed_commit(),
        "route_signature": "GET___RUNTIME_INCIDENT_V116",
        "language_policy_version": LANGUAGE_POLICY_VERSION,
        "provider_runtime_version": INCIDENT_PROBE_PROVIDER_RUNTIME_REVISION,
        "started_at": _APP_STARTED_AT,
        "environment": env,
    }


class IncidentLanguageDryRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    profile: str = "default"

    @field_validator("message")
    @classmethod
    def incident_msg(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Message vide")
        if len(v) > 2000:
            raise ValueError("Message trop long (2000 caractères max)")
        return v


@app.post("/__debug/language-dry-run", include_in_schema=False)
def incident_language_dry_run(req: IncidentLanguageDryRunRequest):
    """SRE V11.6 : chemin langue + garde forced-FR sans appel LLM (guest sec)."""
    from app.api.chat import ChatRequest, assemble_chat_generation_inputs

    stub_user = {
        "is_guest": True,
        "guest_session_id": "incident-probe",
        "ip": "127.0.0.1",
    }
    cr = ChatRequest(message=req.message, profile=(req.profile or "").strip())
    b = assemble_chat_generation_inputs(cr, user=stub_user, persist_memory_side_effects=False)
    pre = ((b.get("system_prompt") or "") + "\n" + (b.get("user_message") or "")).strip()
    snippets = _incident_forced_french_line_snippets(pre)
    if not snippets:
        spost = (
            (b.get("sanitized_system_prompt") or "") + "\n" + (b.get("sanitized_user_message") or "")
        ).strip()
        snippets = _incident_forced_french_line_snippets(spost)

    return {
        "detected_language": b["detected_language"],
        "final_language": b["final_language_hint"],
        "language_instruction": b["lang_instruction"],
        "prompt_contains_forced_french": b["prompt_contains_forced_french"],
        "memory_contains_forced_french": b["memory_contains_forced_french"],
        "profile_contains_forced_french": b["profile_contains_forced_french"],
        "system_contains_forced_french": b["system_core_contains_forced_french"],
        "forced_french_source_type": b["forced_french_source_type"],
        "forced_french_snippets_redacted": snippets,
        "sanitized_still_contains_forced_french": b["provider_prompt_contains_forced_french"],
    }


class ChatLanguageDryRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    profile: str = ""


@app.post("/health/language/chat-dry-run")
def health_language_chat_dry_run(req: ChatLanguageDryRunRequest):
    """Simule l'assemblage du chemin /chat sans appel LLM ni effets de persistance mémoire."""
    from app.api.chat import ChatRequest, assemble_chat_generation_inputs

    stub_user = {
        "is_guest": True,
        "guest_session_id": "dry-run",
        "ip": "127.0.0.1",
    }
    cr = ChatRequest(message=req.message.strip(), profile=(req.profile or "").strip())
    b = assemble_chat_generation_inputs(cr, user=stub_user, persist_memory_side_effects=False)
    return {
        "route_used": "POST /chat",
        "handler_name": "handle_chat_request",
        "chat_routes_production": ["POST /chat", "POST /api/chat"],
        "profile_used": b["profile_used"],
        "response_language_mode": b.get("response_language_mode"),
        "language_source": b.get("language_source"),
        "detected_language": b["detected_language"],
        "final_language": b["final_language_hint"],
        "forced_french_runtime_detected": b["forced_french_runtime_detected"],
        "forced_french_runtime_removed": b["forced_french_runtime_removed_preview"],
        "forced_french_source_type": b["forced_french_source_type"],
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


@app.get("/memory/semantic/search")
def memory_semantic_search_route(
    q: str = Query(default=""),
    project_name: str = Query(default=""),
    memory_type: str = Query(default=""),
    language: str = Query(default=""),
    archived: bool | None = Query(default=None),
    contradicted: bool | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=30),
):
    from app.memory import faiss_memory as fsm

    filters = {
        "project_name": (project_name or "").strip(),
        "memory_type": (memory_type or "").strip(),
        "language": (language or "").strip(),
        "archived": archived,
        "contradicted": contradicted,
    }
    return fsm.search_semantic_memory((q or "").strip(), top_k=limit, filters=filters)


@app.get("/memory/semantic/stats")
def memory_semantic_stats_route():
    from app.memory import faiss_memory as fsm

    return fsm.get_semantic_index_stats()


@app.get("/memory/semantic/health")
def memory_semantic_health_route(window: int = Query(default=50, ge=1, le=120)):
    from app.memory import fractal_memory as fm

    return fm.get_semantic_health(window=window)


@app.post("/memory/semantic/rebuild")
def memory_semantic_rebuild_route(incremental: bool = Query(default=False)):
    from app.memory import faiss_memory as fsm

    return fsm.rebuild_semantic_index(incremental=bool(incremental))


@app.get("/memory/semantic/worker/status")
def memory_semantic_worker_status_route():
    from app.memory import semantic_indexing_worker as siw

    return siw.get_semantic_worker_status()


@app.post("/memory/semantic/worker/run-once")
def memory_semantic_worker_run_once_route():
    from app.memory import semantic_indexing_worker as siw

    return siw.process_semantic_index_queue()


@app.get("/memory/semantic/cache/stats")
def memory_semantic_cache_stats_route():
    from app.memory import embedding_cache as ec

    return ec.embedding_cache_stats()


@app.get("/memory/importance/health")
def memory_importance_health_route():
    from app.memory import fractal_memory as fm

    rows = fm.entries_snapshot_for_tests()
    if not rows:
        return {"status": "ok", "entries": 0}
    with_exp = [e for e in rows if str(e.get("importance_explanation") or "").strip()]
    avg_imp = sum(float(e.get("importance_score") or 0.0) for e in rows) / max(1, len(rows))
    avg_rec = sum(float(e.get("recurrence_score") or 0.0) for e in rows) / max(1, len(rows))
    avg_risk = sum(float(e.get("contradiction_risk") or 0.0) for e in rows) / max(1, len(rows))
    return {
        "status": "ok",
        "entries": len(rows),
        "with_explanations": len(with_exp),
        "avg_importance_score": round(avg_imp, 4),
        "avg_recurrence_score": round(avg_rec, 4),
        "avg_contradiction_risk": round(avg_risk, 4),
    }


@app.post("/memory/importance/refresh")
def memory_importance_refresh_route():
    from app.memory import memory_importance as mi

    return mi.refresh_importance_scores()


@app.get("/memory/importance/top")
def memory_importance_top_route(limit: int = Query(default=20, ge=1, le=100)):
    from app.memory import fractal_memory as fm

    rows = fm.entries_snapshot_for_tests()
    rows.sort(
        key=lambda e: (
            float(e.get("importance_score") or 0.0),
            float(e.get("long_term_value") or 0.0),
            str(e.get("timestamp") or ""),
        ),
        reverse=True,
    )
    out = []
    for e in rows[:limit]:
        out.append(
            {
                "id": e.get("id"),
                "memory_type": e.get("memory_type"),
                "project_name": e.get("project_name"),
                "summary": str(e.get("summary") or "")[:260],
                "importance_score": float(e.get("importance_score") or 0.0),
                "recurrence_score": float(e.get("recurrence_score") or 0.0),
                "semantic_density": float(e.get("semantic_density") or 0.0),
                "contradiction_risk": float(e.get("contradiction_risk") or 0.0),
                "long_term_value": float(e.get("long_term_value") or 0.0),
                "importance_updated_at": e.get("importance_updated_at"),
            }
        )
    return {"status": "ok", "items": out}


@app.get("/memory/importance/explain/{memory_id}")
def memory_importance_explain_route(memory_id: str):
    from app.memory import fractal_memory as fm

    mid = (memory_id or "").strip()
    if not mid:
        raise HTTPException(status_code=400, detail="memory_id manquant")
    rows = fm.entries_snapshot_for_tests()
    for e in rows:
        if str(e.get("id") or "") != mid:
            continue
        return {
            "status": "ok",
            "memory_id": mid,
            "importance_score": float(e.get("importance_score") or 0.0),
            "recurrence_score": float(e.get("recurrence_score") or 0.0),
            "semantic_density": float(e.get("semantic_density") or 0.0),
            "contradiction_risk": float(e.get("contradiction_risk") or 0.0),
            "long_term_value": float(e.get("long_term_value") or 0.0),
            "importance_explanation": str(e.get("importance_explanation") or ""),
            "importance_updated_at": e.get("importance_updated_at"),
        }
    raise HTTPException(status_code=404, detail="Mémoire introuvable")


@app.get("/memory/graph/stats")
def memory_graph_stats_route():
    from app.memory import graph_persistence as gp

    return gp.graph_stats()


@app.get("/memory/graph/hubs")
def memory_graph_hubs_route(limit: int = Query(default=20, ge=1, le=100)):
    from app.memory import fractal_memory as fm

    rows = fm.entries_snapshot_for_tests()
    hubs = sorted(
        [
            {
                "id": e.get("id"),
                "summary": str(e.get("summary") or "")[:220],
                "cluster_id": e.get("cluster_id"),
                "graph_degree": int(e.get("graph_degree") or 0),
                "graph_centrality": float(e.get("graph_centrality") or 0.0),
                "concept_tags": (e.get("concept_tags") or [])[:16],
            }
            for e in rows
        ],
        key=lambda x: (float(x["graph_centrality"]), int(x["graph_degree"])),
        reverse=True,
    )
    return {"status": "ok", "items": hubs[:limit]}


@app.get("/memory/graph/related/{memory_id}")
def memory_graph_related_route(memory_id: str, limit: int = Query(default=12, ge=1, le=60)):
    from app.memory import memory_relationship_graph as mrg

    return {"status": "ok", "memory_id": memory_id, "items": mrg.find_related_memories(memory_id, limit=limit)}


@app.post("/memory/graph/rebuild")
def memory_graph_rebuild_route():
    from app.memory import graph_persistence as gp

    return gp.rebuild_relationship_graph(persist_entries=True)


@app.get("/memory/graph/explain/{memory_id}")
def memory_graph_explain_route(memory_id: str):
    from app.memory import memory_relationship_graph as mrg

    out = mrg.explain_memory_relationships(memory_id)
    if str(out.get("status") or "") != "ok":
        raise HTTPException(status_code=404, detail="Mémoire introuvable")
    return out


@app.get("/memory/temporal/snapshot")
def memory_temporal_snapshot_route():
    from app.memory import memory_temporal_evolution as mte

    snap = mte.build_temporal_snapshot()
    return {
        "status": "ok",
        "updated": snap.get("updated"),
        "rising_count": len(snap.get("rising_concepts") or []),
        "declining_count": len(snap.get("declining_concepts") or []),
        "stale_decisions_count": len(snap.get("stale_decisions") or []),
        "growing_contradictions_count": len(snap.get("growing_contradictions") or []),
        "cluster_evolution": snap.get("cluster_evolution") or [],
    }


@app.post("/memory/temporal/refresh")
def memory_temporal_refresh_route():
    from app.memory import memory_temporal_evolution as mte

    return mte.refresh_temporal_evolution()


@app.get("/memory/temporal/rising")
def memory_temporal_rising_route(limit: int = Query(default=20, ge=1, le=100)):
    from app.memory import memory_temporal_evolution as mte

    rows = mte.detect_rising_concepts(mte.build_temporal_snapshot().get("entries") or [])
    return {"status": "ok", "items": rows[:limit]}


@app.get("/memory/temporal/declining")
def memory_temporal_declining_route(limit: int = Query(default=20, ge=1, le=100)):
    from app.memory import memory_temporal_evolution as mte

    rows = mte.detect_declining_concepts(mte.build_temporal_snapshot().get("entries") or [])
    return {"status": "ok", "items": rows[:limit]}


@app.get("/memory/temporal/explain/{memory_id}")
def memory_temporal_explain_route(memory_id: str):
    from app.memory import memory_temporal_evolution as mte

    out = mte.explain_temporal_evolution(memory_id)
    if str(out.get("status") or "") != "ok":
        raise HTTPException(status_code=404, detail="Mémoire introuvable")
    return out


@app.get("/memory/contradictions/candidates")
def memory_contradictions_candidates_route():
    from app.memory import memory_contradiction_resolution as mcr

    return {"status": "ok", "items": mcr.detect_resolution_candidates()}


@app.post("/memory/contradictions/refresh")
def memory_contradictions_refresh_route():
    from app.memory import memory_contradiction_resolution as mcr

    return mcr.refresh_contradiction_resolutions()


@app.get("/memory/contradictions/report")
def memory_contradictions_report_route():
    from app.memory import memory_contradiction_resolution as mcr

    return mcr.build_contradiction_resolution_report()


@app.get("/memory/contradictions/explain/{memory_id}")
def memory_contradictions_explain_route(memory_id: str):
    from app.memory import memory_contradiction_resolution as mcr

    out = mcr.explain_contradiction_resolution(memory_id)
    if str(out.get("status") or "") != "ok":
        raise HTTPException(status_code=404, detail="Mémoire introuvable")
    return out


@app.post("/memory/contradictions/resolve")
def memory_contradictions_resolve_route(req: MemoryContradictionResolveRequest):
    from app.memory import fractal_memory as fm
    from app.memory import memory_contradiction_resolution as mcr

    with fm._STORE_LOCK:  # noqa: SLF001
        rows = [fm._ensure_entry_defaults(dict(e)) for e in fm._load_entries()]  # noqa: SLF001
        out = mcr.resolve_memory_contradiction(
            rows,
            winner_memory_id=req.winner_memory_id,
            loser_memory_id=req.loser_memory_id,
            reason=req.reason,
            mode=req.mode,
        )
        if str(out.get("status") or "") != "ok":
            raise HTTPException(status_code=400, detail=str(out.get("detail") or "resolution_failed"))
        fm._save_entries(rows)  # noqa: SLF001
    return out


@app.get("/memory/context/build")
def memory_context_build_route(q: str = "", limit: int = Query(default=14, ge=4, le=80)):
    from app.memory import memory_decision_context as mdc

    return mdc.build_decision_context(query=q, limit=limit)


@app.get("/memory/context/explain")
def memory_context_explain_route(q: str = "", limit: int = Query(default=14, ge=4, le=80)):
    from app.memory import memory_decision_context as mdc

    ctx = mdc.build_decision_context(query=q, limit=limit)
    return mdc.explain_context_selection(ctx)


@app.get("/memory/context/risk")
def memory_context_risk_route(q: str = "", limit: int = Query(default=14, ge=4, le=80)):
    from app.memory import memory_decision_context as mdc

    ctx = mdc.build_decision_context(query=q, limit=limit)
    return {
        "status": "ok",
        "context_risk": float(ctx.get("context_risk") or 0.0),
        "unresolved_conflicts": len(ctx.get("unresolved_conflicts") or []),
        "human_review_required": sum(1 for x in (ctx.get("unresolved_conflicts") or []) if bool(x.get("human_review_required"))),
    }


@app.get("/memory/context/stability")
def memory_context_stability_route(q: str = "", limit: int = Query(default=14, ge=4, le=80)):
    from app.memory import memory_decision_context as mdc

    ctx = mdc.build_decision_context(query=q, limit=limit)
    return {
        "status": "ok",
        "context_stability": float(ctx.get("context_stability") or 0.0),
        "context_confidence": float(ctx.get("context_confidence") or 0.0),
        "fragmentation_score": float(ctx.get("fragmentation_score") or 0.0),
    }


@app.get("/memory/context/clusters")
def memory_context_clusters_route(q: str = "", limit: int = Query(default=14, ge=4, le=80)):
    from app.memory import memory_decision_context as mdc

    ctx = mdc.build_decision_context(query=q, limit=limit)
    return {"status": "ok", "active_clusters": ctx.get("active_clusters") or []}


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


@app.get("/decision/arbitration/last")
def decision_arbitration_last_route():
    from app.decision import decision_arbitration as dar

    return dar.get_last_arbitration()


@app.post("/decision/arbitration/simulate")
def decision_arbitration_simulate_route(req: DecisionArbitrationSimulateRequest):
    from app.decision import decision_arbitration as dar
    from app.memory import memory_decision_context as mdc

    ctx = mdc.build_decision_context(query=req.decision_type, limit=18)
    opts = [
        {
            "option_id": str(o.option_id or ""),
            "title": str(o.title or ""),
            "source_memory_ids": list(o.source_memory_ids or []),
            "strategy_type": str(o.strategy_type or ""),
        }
        for o in (req.options or [])
    ]
    return dar.arbitrate_decision(
        project=str(req.project or ""),
        decision_type=str(req.decision_type or ""),
        options=opts,
        context=ctx,
    )


@app.get("/decision/arbitration/report")
def decision_arbitration_report_route():
    from app.decision import decision_arbitration as dar

    last = dar.get_last_arbitration()
    if str(last.get("status") or "") == "empty":
        return {"status": "empty", "selected_option": None, "options": []}
    return last


@app.get("/decision/arbitration/explain/{option_id}")
def decision_arbitration_explain_route(option_id: str):
    from app.decision import decision_arbitration as dar

    oid = str(option_id or "").strip()
    if not oid:
        raise HTTPException(status_code=400, detail="option_id manquant")
    last = dar.get_last_arbitration()
    for o in last.get("options") or []:
        if str(o.get("option_id") or "") != oid:
            continue
        return {"status": "ok", "option": o}
    raise HTTPException(status_code=404, detail="Option introuvable")


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
