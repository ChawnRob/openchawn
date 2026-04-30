<<<<<<< HEAD
import logging
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

    _load_provider("mistral", "app.providers.mistral_provider", "MistralProvider")
    _load_provider("minimax", "app.providers.minimax_provider", "MinimaxProvider")
    _load_provider("ollama", "app.providers.ollama_provider", "OllamaProvider")
    _load_provider("openai", "app.providers.openai_provider", "OpenAIProvider")
    _load_provider("kimi", "app.providers.kimi_provider", "KimiProvider")

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
    "Tu ne mentionnes JAMAIS Mistral AI, OpenAI, ou un autre provider. "
    "Si on te demande qui tu es, réponds : 'Je suis OpenChawn, un système d'orchestration d'intelligence artificielle conçu pour analyser et utiliser les meilleurs modèles selon la situation.' "
    "Réponds brièvement et directement. Ne répète jamais la question. Pas d'introduction. Pas d'explication sauf si demandé."
)


def handle(prompt: str) -> dict:
    providers = get_registry()
    clean_prompt = f"{_SYSTEM}\n\nQuestion: {prompt}"

    for name in ["mistral", "minimax", "ollama", "openai", "kimi"]:
        provider = providers.get(name)
        if not provider:
            continue

        try:
            if hasattr(provider, "is_available") and not provider.is_available():
                print(f"[DEBUG] {name} unavailable")
                continue

            # injecter system prompt si le provider le supporte
            if hasattr(provider, "generate") and "system_prompt" in provider.generate.__code__.co_varnames:
                result = provider.generate(prompt, system_prompt=_SYSTEM)
            else:
                result = provider.generate(promp, system_prompt=_SYSTEM)
            text = _as_text(result)

            print(f"[DEBUG] {name} => {text}")

            if text and text.strip():
                return {
                    "output": text.strip(),
                    "provider": name
                }

        except Exception as e:
            print(f"[router] {name} failed:", e)

    return {
        "output": "Je suis OpenChawn. Aucun modèle n’a répondu pour le moment.",
        "provider": "fallback"
    }
=======
def handle(prompt: str):
    p = prompt.lower()

    # 🧠 PRIORITÉ : compress
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
        except Exception as e:
            pass

        return {
            "action": "MEMORY_COMPRESS",
            "output": {"status": "done", "report": report},
        }

    # 📖 Lecture mémoire
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
>>>>>>> 3b574f3bedca39618e1e690171b52968536d0b88
