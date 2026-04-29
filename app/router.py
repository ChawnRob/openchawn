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

_SYSTEM = "Réponds uniquement avec la réponse finale. Ne répète jamais la question. Ne fais aucune introduction. Pas d'explication sauf si demandé."


def handle(prompt: str) -> dict:
    providers = get_registry()
    clean_prompt = f"Réponds uniquement avec la réponse finale.\nNe répète jamais la question.\nNe fais aucune phrase inutile.\nPas d'explication.\n\nQuestion: {prompt}"

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
                result = provider.generate(clean_prompt)
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
