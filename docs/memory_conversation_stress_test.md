# Stress test conversationnel — mémoire fractale V11.6

## Objectif

Valider les chemins **`/chat` + mémoire** sous charge conversationnelle légère, sans serveur externe ni LLM réel.

## Exécution

```bash
cd /chemin/vers/openchawn
.venv/bin/python scripts/stress_test_memory_conversation.py
```

Échec si un scénario échoue (`exit code 1`). Succès si les 7 scénarios passent (`exit code 0`).

## Principes techniques

| Point | Détail |
|-------|--------|
| Store JSON | Chemin isolé sous `/tmp`, via `STORE_PATH` (pas de pollution de `data/memory/fractal_memory.json`). |
| Backend | `MEMORY_BACKEND=json` forcé dans le script (compatible Railway/CI où Postgres peut être vide). |
| Auth | Override FastAPI sur `get_current_user_or_guest` (`TestClient`). |
| LLM | `generate_response` stubé dans `app.api.chat` — aucun vecteur ni embedding. |
| Anti rate-limit `/chat` | Middleware : garde ~2 s par acteur — le script envoie un **`Authorization: Bearer` unique par requête** (les 12 premiers caractères du token diffèrent). |

**Endpoint testé :** **`POST /chat`** (routes montées sans préfixe `/api` dans l’application actuelle).

## Scénarios couverts

1. **Mémoire stable** — assertion DeepSeek + Railway dans réponse ou contexte reconstruit après deux tours `/chat`.
2. **Préférence utilisateur** — ByteByteGo présent dans un `build_layered_memory_context` ciblé.
3. **Contradiction Ollama** — second message formulé avec **« fournisseur »** (évite la voie `Decision/Concept: provider` sans « ollama » dans le pivot concept) pour que **`contradiction_detected`** remonte dans le store / lifecycle / observability.
4. **Anti-bruit** — dix messages banals puis contexte encore dominé par signaux DeepSeek ou préférence pertinentes (heuristique légère).
5. **Renforcement** — trois fois la même question Anglo-française avec mots-clés **OpenChawn / DeepSeek / Railway** dans `/chat`, puis contrôle **`access_count`** incrémental sur des entrées lien DeepSeek/Railway.
6. **Archive** — injection d’une entrée faible, ancienne, sans accès ; vérif **`lifecycle_status=archived`** après lifecycle.
7. **`GET /memory/last-context`** — première entrée enrichie avec `why_selected`, scores, **`retrieval_rank`**.

À la fin, la console imprime **`tests_passed`** / **`tests_failed`**, un extrait **`top_memories`**, ainsi que **`contradictions_detected`** et **`memory_health_score`** depuis les endpoints de santé.

## Hors périmètre volontaire

**Timeline UI**, **memory graph UI**, **semantic explorer** — non implémentés (réutilise la même note conceptuelle que les autres endpoints mémoire).
