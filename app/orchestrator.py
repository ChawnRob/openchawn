from __future__ import annotations
from dataclasses import dataclass, asdict
import logging

from app.router import handle as router_handle
from app.memory.store import MemoryStore
from app.memory.context import ContextBuilder

log = logging.getLogger("openchawn.orchestrator")

_RETRY_THRESHOLD = 0.5
_MAX_RETRIES = 1


def handle(prompt: str, raw_message: str = "") -> dict:
    """Backward-compatible alias for the router entrypoint."""
    return router_handle(prompt, raw_message=raw_message)


@dataclass
class PipelineStep:
    source_module: str
    action: str
    reason: str
    input_summary: str
    output_summary: str
    confidence: float


def _summary(text: str, n: int = 140) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:n] + ("..." if len(text) > n else "")


def _load_provider(name: str):
    mapping = {
        "openrouter": ("app.providers.openrouter_provider", "OpenRouterProvider"),
        "deepseek": ("app.providers.deepseek_provider", "DeepSeekProvider"),
        "kimi": ("app.providers.kimi_provider", "KimiProvider"),
        "openai": ("app.providers.openai_provider", "OpenAIProvider"),
    }
    if name not in mapping:
        return None
    mod, cls = mapping[name]
    try:
        return getattr(__import__(mod, fromlist=[cls]), cls)()
    except Exception as e:
        log.info(f"provider {name} indisponible ({e.__class__.__name__})")
        return None


def _call(provider, prompt: str, system_prompt: str = "") -> tuple[str, float]:
    if provider is None:
        return "", 0.0
    try:
        if not provider.is_available():
            return "", 0.0
        try:
            out = provider.generate(prompt, system_prompt=system_prompt)
        except TypeError:
            out = provider.generate(prompt)
        return (out or ""), 0.7
    except Exception as e:
        log.warning(f"provider call failed: {e}")
        return "", 0.0


def _safe_step(name: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        log.error(f"step {name} crashed: {e}")
        err_step = PipelineStep(
            source_module=name,
            action="error",
            reason=f"{e.__class__.__name__}",
            input_summary="",
            output_summary=f"ERROR: {str(e)[:120]}",
            confidence=0.0,
        )
        return err_step, None


def step_mempalace(prompt: str, project: str):
    hits = []
    conf = 0.0
    try:
        from app.mempalace import search_memory
        results = search_memory(prompt, project=project, top_k=5, touch=True)
        hits = [
            {"id": h.entry.id, "type": h.entry.type,
             "content": h.entry.content, "score": round(h.score, 3)}
            for h in results
        ]
        if hits:
            conf = max(h["score"] for h in hits)
    except Exception as e:
        log.warning(f"mempalace step indisponible: {e}")
    return PipelineStep(
        source_module="MemPalace",
        action="memory_search",
        reason="retrouver les elements utiles du passe",
        input_summary=_summary(prompt),
        output_summary=f"{len(hits)} souvenirs pertinents",
        confidence=round(conf, 2),
    ), hits


def step_asi_evolve(prompt: str, project: str, user_id: str, feedback: str = ""):
    decision = {"decision": "MODEL_CALL_NEEDED", "confidence": 0.5,
                "reason": "asi-evolve indisponible"}
    try:
        from app.asi_evolve.decision import decide
        full = prompt if not feedback else f"{prompt}\n[FEEDBACK PRECEDENT]: {feedback}"
        decision = decide(full, project=project, user_id=user_id)
    except Exception as e:
        log.warning(f"asi-evolve indisponible: {e}")
    return PipelineStep(
        source_module="ASI-evolve",
        action="decide_and_adapt" if not feedback else "re_adapt_with_feedback",
        reason=(decision.get("reason") or "adapter le routage selon contexte")[:160],
        input_summary=_summary(prompt),
        output_summary=f"decision={decision.get('decision','?')}",
        confidence=float(decision.get("confidence", 0.5) or 0.0),
    ), decision


def step_kimi(prompt: str):
    p = _load_provider("kimi")
    out, conf = _call(p,
        prompt=f"Donne en 3 lignes le contexte culturel et les nuances utiles :\n{prompt}",
        system_prompt="Tu enrichis le contexte culturel. Bref et pertinent.")
    return PipelineStep(
        source_module="Kimi",
        action="cultural_context",
        reason="enrichir le contexte culturel et les nuances",
        input_summary=_summary(prompt),
        output_summary=_summary(out),
        confidence=round(conf, 2),
    ), out


def step_minimax(prompt: str, kimi_ctx: str):
    """Optimisation via DeepSeek (ex étape Minimax)."""
    p = _load_provider("deepseek")
    full = f"Question: {prompt}\nContexte culturel: {kimi_ctx or '(aucun)'}\n\nReformule la question de maniere optimale et concise."
    out, conf = _call(p, prompt=full,
        system_prompt="Tu optimises la requete pour clarte et precision.")
    return PipelineStep(
        source_module="DeepSeek",
        action="optimize",
        reason="optimiser la formulation et l efficacite",
        input_summary=_summary(prompt),
        output_summary=_summary(out),
        confidence=round(conf, 2),
    ), out


def step_mistral(prompt: str, optimized: str):
    """Structuration via OpenRouter (ex étape Mistral)."""
    p = _load_provider("openrouter")
    base = optimized or prompt
    full = f"Question optimisee: {base}\n\nDecompose la reponse en etapes logiques claires."
    out, conf = _call(p, prompt=full,
        system_prompt="Tu structures la logique de la reponse en etapes claires.")
    return PipelineStep(
        source_module="OpenRouter",
        action="structure_logic",
        reason="structurer la logique de la reponse",
        input_summary=_summary(base),
        output_summary=_summary(out),
        confidence=round(conf, 2),
    ), out


def step_ollama(prompt: str, mem_hits: list, kimi: str, minimax: str, mistral: str):
    mem_block = "\n".join(f"- {h['content']}" for h in mem_hits[:3]) or "(aucun)"
    full = (
        f"Question utilisateur: {prompt}\n\n"
        f"Memoire pertinente:\n{mem_block}\n\n"
        f"Contexte culturel (Kimi): {kimi or '(aucun)'}\n\n"
        f"Question optimisee (DeepSeek): {minimax or '(aucune)'}\n\n"
        f"Structure logique (OpenRouter): {mistral or '(aucune)'}\n\n"
        f"Genere la reponse finale claire et utile dans la langue attendue par l'utilisateur."
    )
    p = _load_provider("openai")
    src = "OpenAI"
    out, conf = _call(p, prompt=full,
        system_prompt="Tu es OpenChawn. Reponds clairement a l utilisateur.")
    if not out:
        out = "[OpenChawn stub] aucun provider de generation disponible."
        conf = 0.1
    return PipelineStep(
        source_module=src,
        action="final_generation",
        reason="generer la reponse finale agregee",
        input_summary=_summary(prompt),
        output_summary=_summary(out),
        confidence=round(conf, 2),
    ), out


def _run_pipeline(prompt: str, project: str, user_id: str, feedback: str = ""):
    trace: list[PipelineStep] = []
    s1, mem  = _safe_step("MemPalace",  step_mempalace,  prompt, project);                trace.append(s1)
    s2, _    = _safe_step("ASI-evolve", step_asi_evolve, prompt, project, user_id, feedback); trace.append(s2)
    s3, kimi = _safe_step("Kimi",       step_kimi,       prompt);                          trace.append(s3)
    s4, mm   = _safe_step("DeepSeek",   step_minimax,    prompt, kimi or "");              trace.append(s4)
    s5, mst  = _safe_step("OpenRouter", step_mistral,    prompt, mm or "");                 trace.append(s5)
    s6, ans  = _safe_step("Final",      step_ollama,     prompt, mem or [], kimi or "", mm or "", mst or ""); trace.append(s6)
    return trace, ans, mem


def _overall_confidence(trace) -> float:
    confs = [s.confidence for s in trace if s.confidence > 0]
    return round(sum(confs) / len(confs), 2) if confs else 0.0


def ask(prompt: str, project: str = "default", user_id: str = "Robert1982") -> dict:
    # --- mémoire conversationnelle : enrichir le prompt ---
    _store = MemoryStore()
    try:
        recent = _store.get_recent(user_id, limit=5)
        # filtrage simple : garder les tours contenant des mots du prompt
        words = set(prompt.lower().split())
        relevant = [t for t in recent if words & set(t.get("content", "").lower().split())]
        if not relevant:
            relevant = recent[-2:]  # fallback : 2 derniers tours
        enriched = prompt
        if relevant:
            _builder = ContextBuilder(_store, max_turns=5)
            enriched = _builder.build_prompt(user_id, prompt)
        log.info(f"memory: {len(recent)} tours, {len(relevant)} pertinents")
    except Exception as e:
        enriched = prompt
        log.warning(f"memory enrichment skipped: {e}")

    trace, ans, mem = _run_pipeline(enriched, project, user_id)
    overall = _overall_confidence(trace)

    retried = False
    if overall < _RETRY_THRESHOLD:
        for _ in range(_MAX_RETRIES):
            feedback = f"reponse precedente faible (confiance={overall})"
            trace2, ans2, mem2 = _run_pipeline(prompt, project, user_id, feedback=feedback)
            overall2 = _overall_confidence(trace2)
            if overall2 > overall:
                trace, ans, mem = trace2, ans2, mem2
                overall = overall2
                retried = True
                break

    try:
        from app.asi_evolve.learn import learn_from_exchange
        learn_from_exchange(
            prompt=prompt, response=ans or "",
            provider="deepseek", tier="economic",
            project=project, user_id=user_id,
        )
    except Exception as e:
        log.info(f"learn skipped: {e}")

    # --- mémoire conversationnelle : sauvegarder le tour ---
    try:
        _store.save_turn(user_id, "user", prompt)
        _store.save_turn(user_id, "assistant", (ans or "")[:500])
        log.info(f"memory: tour sauvegarde pour {user_id}")
    except Exception as e:
        log.warning(f"memory save skipped: {e}")

    return {
        "answer": ans or "[stub]",
        "confidence": overall,
        "retried": retried,
        "trace": [asdict(s) for s in trace],
    }
