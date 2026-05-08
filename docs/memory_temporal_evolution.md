# Memory Temporal Evolution Layer V11.6

## Role
Le layer temporel suit l'evolution des memoires, concepts et clusters dans le temps, sans LLM, sans cloud, sans dependance externe.

Objectifs:
- detecter les concepts qui montent ou declinent;
- identifier les decisions devenues stale;
- detecter les contradictions qui croissent;
- exposer des signaux simples pour retrieval, consolidation, graph, importance, FAISS.

## Temporal Status
Champs ajoutes par memoire:
- `first_seen_at`
- `last_seen_at`
- `trend_score` (`-1.0..1.0`)
- `momentum_score` (`-1.0..1.0`)
- `stability_score` (`0.0..1.0`)
- `volatility_score` (`0.0..1.0`)
- `temporal_status` in `rising|stable|declining|stale|volatile|unresolved`
- `temporal_explanation`
- `temporal_updated_at`

Regles V11.6:
- reutilisation frequente + importance haute => `rising`
- concept central stable + faible contradiction => `stable`
- memoire ancienne jamais re-utilisee => `declining` ou `stale`
- contradiction repetee => `unresolved` / croissance contradiction
- cluster avec signaux recents forts => `rising`
- memoires sensibles (secrets/tokens/api keys) exclues

## Endpoints
- `GET /memory/temporal/snapshot`
- `POST /memory/temporal/refresh`
- `GET /memory/temporal/rising`
- `GET /memory/temporal/declining`
- `GET /memory/temporal/explain/{memory_id}`

## Integrations
- retrieval: boost leger via `trend_score`
- consolidation scheduler: prise en compte `stale_decisions` et `rising_clusters`
- relationship graph: exposition de `temporal_status`
- importance scoring: `momentum_score` alimente la valeur long-terme
- decision engine debug: expose `temporal_explanation`
- FAISS indexing: priorite aux memoires `rising`/`stable` a forte valeur long-terme

## MVP Limits
- heuristiques deterministes locales uniquement
- pas de prediction probabiliste avancee
- pas de modele sequence externe
- precision dependante de la qualite des metadonnees (`access_count`, timestamps, contradictions)

## Future
- prediction layer (forecast court/moyen terme)
- pondération contextuelle par etat cognitif
- raisonnement temporel type JEPA / world-model
- version Postgres/Neo4j avec snapshots temporels historises

