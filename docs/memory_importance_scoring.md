# Memory Importance Scoring Layer V11.6

## Rôle

`memory_importance.py` enrichit chaque mémoire avec des signaux heuristiques exploitables par:

- retrieval ranking,
- compression,
- consolidation,
- indexation semantic (FAISS),
- archivage,
- decision engine debug.

## Champs enrichis

Chaque mémoire reçoit/mise à jour:

- `importance_score`
- `recurrence_score`
- `semantic_density`
- `contradiction_risk`
- `long_term_value`
- `importance_explanation`
- `importance_updated_at`
- `indexable` (protection secrets)

## Scoring heuristique (MVP)

Signaux utilisés:

- `memory_type`, `memory_level`, `project_name`
- `access_count`, `metadata.retrieval_hits`
- `metadata.merge_count`
- `metadata.linked_concept_id`
- `contradiction_detected`
- `lifecycle_status`
- `metadata.compressed_into`
- `tags`, recency
- `semantic_match` (indirectement via retrieval metadata déjà persistées)

Règles clés:

1. `system` > bruit `session`.
2. `compressed` stable > raw dupliquée (`compressed_into`).
3. contradiction non résolue augmente `contradiction_risk`.
4. accès répétés augmentent `recurrence_score`.
5. lien conceptuel central augmente `long_term_value`.
6. secrets/API keys/tokens => `importance_score=0` + `indexable=false`.
7. bruit faible (`ok/merci/salut`) pénalisé.
8. sujets architecture/provider/Railway/sécurité/mémoire favorisés.

## Intégrations V11.6

- Retrieval: `build_layered_memory_context` refresh heuristique avant ranking.
- Compression: clusters triés aussi par `avg_long_term_value`.
- Consolidation: pression mémoire modulée par importance+risk.
- FAISS: priorise indexation par `long_term_value` et ignore `indexable=false`.
- Archive rules: archive seulement si faible importance ET faible récurrence.
- Decision engine: expose `importance_explanation` en debug décision.

## Endpoints

- `GET /memory/importance/health`
- `POST /memory/importance/refresh`
- `GET /memory/importance/top`
- `GET /memory/importance/explain/{memory_id}`

## Limites MVP

- Heuristiques déterministes, sans contexte sémantique profond.
- Pas de calibration automatique par feedback utilisateur.
- Sensibilité dépendante des patterns secrets existants.

## Évolutions futures

- scoring LLM contrôlé (optionnel, sandboxé, auditable),
- poids émotionnel/QEI,
- consolidation de signaux multi-sessions via backend Postgres/Redis.

