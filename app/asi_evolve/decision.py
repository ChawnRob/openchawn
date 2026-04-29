from __future__ import annotations
import re
from typing import Optional, Literal
from app.mempalace import search_memory, load_memories, MemoryType
from app.asi_evolve.human_layer import analyze_human

Decision = Literal[
    "MEMORY_READ",
    "MEMORY_WRITE",
    "MEMORY_COMPRESS",
    "MODEL_CALL_NEEDED",
    "SYSTEM_IMPROVEMENT",
]

# ─── Signaux d'intention ──────────────────────────────────────────────────
_WRITE_RE = re.compile(
    r"\b(retiens|rappelle[- ]toi|note que|enregistre|remember that|save this|stocke)\b",
    re.I,
)
_COMPRESS_RE = re.compile(
    r"\b(compresse|consolide|r[ée]sume la m[ée]moire|nettoie la m[ée]moire|compress memory)\b",
    re.I,
)
_SYSTEM_RE = re.compile(
    r"\b(am[ée]liore[- ]toi|upgrade syst[eè]me|refactor (asi|openchawn|syst[eè]me)|"
    r"change l'archi|optimise le syst[eè]me|self[- ]improve|[ée]volue toi[- ]m[ée]me)\b",
    re.I,
)
_CODE_RE = re.compile(
    r"\b(code|fonction|class|bug|stacktrace|impl[ée]mente|api|endpoint|refactor|debug)\b",
    re.I,
)
_REASON_RE = re.compile(
    r"\b(analyse|raison|d[ée]montre|prouve|compare|strat[ée]g|pourquoi|explain)\b", re.I
)
_LOCAL_RE = re.compile(r"\b(local only|offline|sans internet|hors ligne)\b", re.I)

# ─── Seuils ───────────────────────────────────────────────────────────────
MEMORY_ANSWER_THRESHOLD = 0.35
COMPRESS_MEMORY_COUNT = 200  # surcharge → suggestion auto de compression


def _detect_write_type(text: str) -> MemoryType:
    t = text.lower()
    if re.search(r"\b(r[eè]gle|rule|contrainte)\b", t):
        return "rule"
    if re.search(r"\b(strat[ée]g|plan|orientation)\b", t):
        return "strategy"
    if re.search(r"\b([ée]chec|failure|incident|bug pass[ée])\b", t):
        return "failure"
    if re.search(r"\b(insight|pattern|apprentissage|observation)\b", t):
        return "insight"
    if re.search(r"\b(d[ée]cision|decided|choisi|valid[ée])\b", t):
        return "decision"
    return "fact"


def _route_models(text: str) -> dict:
    """Respecte la cible 70 % mémoire / 20 % éco / 10 % premium."""
    if _LOCAL_RE.search(text):
        return {
            "tier": "local",
            "chain": ["ollama"],
            "temperature": 0.5,
            "reason": "Contrainte local_only détectée.",
        }
    if _CODE_RE.search(text) or _REASON_RE.search(text):
        return {
            "tier": "premium",
            "chain": ["kimi", "minimax", "mistral", "ollama"],
            "temperature": 0.2 if _CODE_RE.search(text) else 0.3,
            "reason": "Tâche code/raisonnement → tier premium (Kimi K2.6).",
        }
    return {
        "tier": "economic",
        "chain": ["minimax", "mistral", "kimi", "ollama"],
        "temperature": 0.6,
        "reason": "Tâche générique → tier éco en priorité (cible 70/20/10).",
    }


def _build(
    *,
    decision: Decision,
    reason: str,
    confidence: float,
    memory_query: Optional[dict],
    memory_update: Optional[dict],
    model_routing: Optional[dict],
    human_layer: dict,
    system_note: Optional[str] = None,
) -> dict:
    return {
        "decision": decision,
        "reason": reason,
        "confidence": round(confidence, 3),
        "memory_query": memory_query,
        "memory_update": memory_update,
        "model_routing": model_routing,
        "human_layer": human_layer,
        "system_note": system_note,
    }


def decide(
    prompt: str,
    *,
    project: str = "openchawn",
    user_id: str = "robert",
) -> dict:
    """
    Cerveau décisionnel ASI-Evolve.
    Local-first : interroge toujours MemPalace avant de suggérer un appel modèle.
    N'effectue AUCUN appel externe ici.
    """
    human = analyze_human(prompt)

    # 1. SYSTEM_IMPROVEMENT — meta sur le système lui-même
    if _SYSTEM_RE.search(prompt):
        return _build(
            decision="SYSTEM_IMPROVEMENT",
            reason="Demande explicite d'évolution du système ASI-Evolve / OpenChawn.",
            confidence=0.88,
            memory_query=None,
            memory_update=None,
            model_routing=None,
            human_layer=human,
            system_note="Modification archi requise — validation humaine obligatoire avant déploiement.",
        )

    # 2. MEMORY_WRITE — enregistrement explicite demandé
    if _WRITE_RE.search(prompt):
        mtype = _detect_write_type(prompt)
        return _build(
            decision="MEMORY_WRITE",
            reason=f"Signal d'enregistrement détecté → type={mtype}.",
            confidence=0.9,
            memory_query=None,
            memory_update={
                "type": mtype,
                "project": project,
                "content": prompt.strip(),
                "source": f"user:{user_id}",
                "importance_score": 0.7,
                "confidence": 0.85,
            },
            model_routing=None,
            human_layer=human,
        )

    # 3. MEMORY_COMPRESS — demande explicite ou surcharge mémoire
    mem_count = len(load_memories())
    if _COMPRESS_RE.search(prompt) or mem_count >= COMPRESS_MEMORY_COUNT:
        return _build(
            decision="MEMORY_COMPRESS",
            reason=(
                "Demande explicite de compression mémoire."
                if _COMPRESS_RE.search(prompt)
                else f"Seuil mémoire dépassé ({mem_count} ≥ {COMPRESS_MEMORY_COUNT})."
            ),
            confidence=0.8,
            memory_query={
                "project": project,
                "status": "active",
                "strategy": "group_by_type_and_summarize",
            },
            memory_update=None,
            model_routing=None,
            human_layer=human,
        )

    # 4. MEMORY_READ — MemPalace suffit
    hits = search_memory(prompt, project=project, top_k=5, touch=False)
    if hits and hits[0].score >= MEMORY_ANSWER_THRESHOLD:
        return _build(
            decision="MEMORY_READ",
            reason=f"Réponse trouvée en mémoire (top score={hits[0].score:.2f}).",
            confidence=min(0.6 + hits[0].score, 0.98),
            memory_query={
                "query": prompt.strip(),
                "project": project,
                "top_k": 5,
                "hits": [
                    {
                        "id": h.entry.id,
                        "score": round(h.score, 3),
                        "type": h.entry.type,
                    }
                    for h in hits
                ],
            },
            memory_update=None,
            model_routing=None,
            human_layer=human,
        )

    # 5. MODEL_CALL_NEEDED — dernier recours, routing 70/20/10
    routing = _route_models(prompt)
    return _build(
        decision="MODEL_CALL_NEEDED",
        reason="Aucune réponse suffisante en mémoire → appel modèle nécessaire.",
        confidence=0.7,
        memory_query={
            "query": prompt.strip(),
            "project": project,
            "top_k": 5,
            "hits": [
                {
                    "id": h.entry.id,
                    "score": round(h.score, 3),
                    "type": h.entry.type,
                }
                for h in hits
            ]
            if hits
            else [],
        },
        memory_update=None,
        model_routing=routing,
        human_layer=human,
    )
