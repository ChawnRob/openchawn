# Semantic Indexing Worker + Embedding Cache (V11.6)

## Rôle

Le worker d'indexation sémantique découple l'écriture mémoire du coût d'indexation/embeddings:

- `/chat` reste non bloquant,
- les embeddings sont calculés en tâche best-effort via queue locale,
- le cache évite les recalculs inutiles.

## Architecture

- `app/memory/semantic_indexing_worker.py`
  - `enqueue_semantic_index_job(memory_id)`
  - `process_semantic_index_queue()`
  - `index_pending_memories()`
  - `get_semantic_worker_status()`
  - `clear_semantic_queue_for_tests()`
- `app/memory/embedding_cache.py`
  - `compute_text_hash(text)`
  - `get_cached_embedding(text_hash)`
  - `set_cached_embedding(text_hash, vector, metadata)`
  - `embedding_cache_stats()`

## Flux

1. `write_exchange` persiste les entrées fractales.
2. `write_exchange` enqueue chaque `memory_id` en best-effort.
3. Le worker `run-once` traite la queue:
   - lit l'entrée mémoire,
   - appelle `faiss_memory.add_memory_embedding`,
   - met à jour compteurs `indexed/skipped/errors`.

## Sécurité

- Aucun appel LLM/network.
- Embeddings locaux uniquement.
- Le cache est basé sur hash de texte normalisé.
- Le cache ne conserve jamais de texte brut.
- Contenu sensible (secret/token/api key) non indexé et non caché.

## Endpoints

- `GET /memory/semantic/worker/status`
- `POST /memory/semantic/worker/run-once`
- `GET /memory/semantic/cache/stats`

## Railway / Prod

- Mode actuel: in-process (sans cron externe), prêt pour MVP Railway.
- Évolution future:
  - remplacer queue locale par Redis/DB queue,
  - exécuter `run-once` depuis worker process séparé,
  - conserver le contrat API identique.

## Compatibilité

- Ne casse pas `/api/chat` (contrat inchangé).
- Ne casse pas la couche FAISS (complémentaire).
- Ne casse pas l'observabilité semantic existante.
- Compatible futur backend Postgres (indexing découplé du write path).

