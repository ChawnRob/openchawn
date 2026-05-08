import logging
from app.core.language_policy import detect_user_language
log = logging.getLogger("openchawn.router")

_REGISTRY = {}

def _load_provider(name, module_path, class_name):
    try:
        module = __import__(module_path, fromlist=[class_name])
        cls = getattr(module, class_name)
        _REGISTRY[name] = cls()
        log.info(f"Provider {name} chargé")
    except Exception as e:
        log.warning(f"Provider {name} non chargé: {e}")

def get_registry():
    if _REGISTRY:
        return _REGISTRY

    _load_provider("deepseek", "app.providers.deepseek_provider", "DeepSeekProvider")
    _load_provider("kimi", "app.providers.kimi_provider", "KimiProvider")
    _load_provider("openai", "app.providers.openai_provider", "OpenAIProvider")
    _load_provider("infomaniak", "app.providers.infomaniak_provider", "InfomaniakProvider")
    _load_provider("openrouter", "app.providers.openrouter_provider", "OpenRouterProvider")

    return _REGISTRY

def _as_text(result):
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return (
            result.get("output")
            or result.get("response")
            or result.get("message")
            or ""
        )
    return str(result)

_SYSTEM = (
    "Tu es OpenChawn, un système d'orchestration d'intelligence artificielle. "
    "Tu ne mentionnes JAMAIS le nom d'un fournisseur de modèle ou moteur externe. "
    "Si on te demande qui tu es, réponds : 'Je suis OpenChawn, un système d'orchestration d'intelligence artificielle conçu pour analyser et utiliser les meilleurs modèles selon la situation.' "
    "Réponds brièvement et directement. Ne répète jamais la question. Pas d'introduction. Pas d'explication sauf si demandé."
)


def handle(prompt: str, raw_message: str = "") -> dict:
    # raw_message = message utilisateur brut (sans contexte mémoire injecté)
    p = (raw_message or prompt).lower()

    # ── Commandes spéciales (avant appel LLM) ──

    # Compress mémoire
    if "consolide" in p or "compresse" in p or "compress" in p:
        report = {
            "total_before": 0,
            "total_after_active": 0,
            "dedup_archived": 0,
            "decay_archived": 0,
            "groups_processed": 0,
        }
        try:
            from app.mempalace import compress
            r = compress()
            report = {
                "total_before": r.total_before,
                "total_after_active": r.total_after_active,
                "dedup_archived": r.dedup_archived,
                "decay_archived": r.decay_archived,
                "groups_processed": r.groups_processed,
            }
        except Exception:
            pass
        return {
            "action": "MEMORY_COMPRESS",
            "output": {"status": "done", "report": report},
        }

    # Lecture mémoire
    if "memoire" in p or "mémoire" in p:
        hits = []
        try:
            from app.mempalace import search_memory
            results = search_memory(prompt, top_k=5, touch=True)
            hits = [
                {
                    "id": h.entry.id,
                    "type": h.entry.type,
                    "content": h.entry.content,
                    "summary": h.entry.summary,
                    "score": round(h.score, 3),
                }
                for h in results
            ]
        except Exception:
            pass
        return {
            "action": "MEMORY_READ",
            "output": hits,
        }

    # ── Appel LLM via providers ──

    providers = get_registry()
    from app.provider_manager import get_provider_manager

    for name in get_provider_manager().resolution_order():
        provider = providers.get(name)
        if not provider:
            continue

        try:
            if hasattr(provider, "is_available") and not provider.is_available():
                log.debug(f"{name} unavailable")
                continue

            result = provider.generate(prompt, system_prompt=_SYSTEM)
            text = _as_text(result)

            log.debug(f"{name} => {text[:80] if text else '(empty)'}")

            if text and text.strip():
                return {
                    "action": "MODEL_CALL_NEEDED",
                    "output": text.strip(),
                    "provider": name,
                }

        except Exception as e:
            log.warning(f"{name} failed: {e}")

    return {
        "action": "MODEL_CALL_NEEDED",
        "output": (
            "I am OpenChawn. No model replied yet."
            if detect_user_language(raw_message or prompt) == "en"
            else "Je suis OpenChawn. Aucun modèle n'a répondu pour le moment."
        ),
        "provider": None,
    }
