# Memory Contradiction Resolution Layer V11.6

## Role
Passer de "contradiction detectee" a une resolution traçable:
- classification du conflit;
- arbitrage heuristique local;
- conservation complete de l'historique (aucune suppression).

## Statuts
- `unresolved`
- `resolved`
- `superseded`
- `deprecated`
- `conflict_active`
- `needs_human_review`

Champs ajoutes:
- `contradiction_resolution_status`
- `superseded_by`
- `supersedes`
- `resolution_reason`
- `resolution_confidence`
- `resolution_updated_at`
- `human_review_required`

## Types de contradiction
- `provider_strategy`
- `production_policy`
- `architecture_decision`
- `security_policy`
- `cost_strategy`
- `memory_policy`
- `temporal_obsolescence`
- `factual_conflict`
- `user_preference_conflict`

## Regles d'arbitrage
- jamais de suppression memoire;
- une memoire recente peut supersede une ancienne;
- importance/long_term_value/centralite favorisent un gagnant;
- archivee est fortement penalisee;
- contradiction risquee => prudence;
- securite/secrets/API keys => `needs_human_review`;
- ambiguite => pas de resolution auto.

## Resolution Auto vs Manuelle
- auto: `POST /memory/contradictions/refresh` classe et resolve les conflits non ambigus.
- manuel: `POST /memory/contradictions/resolve` avec `winner_memory_id`, `loser_memory_id`, `reason`, `mode`.

## Endpoints
- `GET /memory/contradictions/candidates`
- `POST /memory/contradictions/refresh`
- `GET /memory/contradictions/report`
- `GET /memory/contradictions/explain/{memory_id}`
- `POST /memory/contradictions/resolve`

## Integrations
- Decision Engine penalise `unresolved/conflict_active`, favorise `resolved`.
- Temporal distingue obsolescence vs supersession.
- Graph conserve liens negatifs et expose le statut de resolution.
- Importance reduit `long_term_value` pour `deprecated/superseded`.
- FAISS n'indexe pas `deprecated`.
- Compression ignore les memoires `unresolved/conflict_active`.

## Limites MVP
- heuristiques locales deterministes;
- pas de raisonnement causal profond multi-episode;
- pas d'annotation humaine avancee (workflow externe).

## Futur
- human-in-the-loop avec validations et audit trail enrichi;
- simulation d'impact global ("world impact");
- conflict simulation temporelle type JEPA/world-model.

