# Mémoire fractale V11.6 — replay & timeline (MVP)

## Objectif

Enregistrer des **événements légers** à chaque cycle de vie mémoire (création, retrieval, renforcement, archivage, concepts, contradictions, contexte injecté) pour permettre un **replay** hors UI : comprendre l’évolution des concepts, repérer les contradictions et reconstruire partiellement le contexte utilisé par le chat.

- **Pas** de vecteurs, embeddings ni nouvelle infra.
- Stockage **MVP** : fichier JSON (`data/memory/memory_timeline.json`), schéma compatible avec une future table Postgres append-only (même champs logiques).

## Schéma d’événement

| Champ | Description |
|--------|-------------|
| `event_id` | Identifiant unique |
| `timestamp` | ISO-8601 UTC |
| `event_type` | Voir liste ci-dessous |
| `memory_id` | Entrée mémoire principale (si pertinent) |
| `memory_type` | `system` \| `project` \| `user` \| `session` |
| `project_name` | Slug projet |
| `summary` | Texte court, **sans secrets** (sanitisation) |
| `importance_score` | Snapshot numérique |
| `decay_score` | Snapshot numérique |
| `lifecycle_status` | Statut observé au moment de l’événement |
| `concept_ids` | Liste d’IDs liés |
| `contradiction_detected` | Booléen |
| `metadata` | Objet JSON (ex. `session_id`, `user_key`, snippets ordonnés pour `context_injected`) |

Types d’événements :

- `memory_created`
- `memory_retrieved`
- `memory_reinforced`
- `memory_archived`
- `concept_created`
- `concept_merged`
- `contradiction_detected`
- `context_injected`

## Stockage

- **Production / dev par défaut** : `data/memory/memory_timeline.json`
- **Tests** : le script de test assigne un fichier temporaire (`memory_timeline.TIMELINE_JSON_PATH`) pour ne pas polluer le store habituel. Le store fractal (`fractal_memory.STORE_PATH`) peut être isolé de la même façon.

Les **clés API / tokens** ne doivent jamais être écrits : filtrage côté écriture mémoire existant + `sanitize_timeline_text` sur les résumés timeline.

## Endpoints HTTP

### `GET /memory/timeline`

Filtre la timeline.

| Paramètre | Description |
|-----------|-------------|
| `project` | Slug ou sous-chaîne normalisée |
| `memory_type` | `system`, `project`, `user`, `session` |
| `event_type` | Un des types listés plus haut |
| `since` | Borne basse ISO (optionnel) |
| `until` | Borne haute ISO (optionnel) |
| `limit` | Défaut 200, max 2000 |

Réponse : `{ "status": "ok", "events": [ ... ] }`

### `GET /memory/replay`

Rejoue une fenêtre filtrée et renvoie une **agrégation** pour analyse.

Paramètres : `project`, `memory_type`, `since`, `until`, `limit` (similaires au timeline ; `memory_type` est optionnel et utile pour réduire le bruit).

Champs principaux :

- `ordered_events` — événements triés chronologiquement puis tronqués selon `limit`
- `reconstructed_context_summary` — concaténation best-effort (retrieval + summaries injectées)
- `key_decisions` — extraits dont l’importance / le libellé ressemble à une décision (`provider`, `DeepSeek`, etc.)
- `contradictions` — événements de contradiction ou créations/concepts marqués contradictoires
- `concept_evolution` — par ID, liste des évolutions vues sur la fenêtre

### `GET /memory/replay/session/{session_id}`

Replay limité aux événements dont `metadata.session_id` correspond.

**Fallback** : si aucun événement ne matche `session_id`, second essai avec `metadata.user_key` égal à `{session_id}` (anciennes entrées sans `session_id` explicite).

### `GET /memory/decision-trace`

| Paramètre | Requis |
|-----------|--------|
| `concept` | Oui (ex. `DeepSeek`) |
| `project` | Non (filtre slug) |

Réponse : `first_seen`, `supporting_memories`, `merged_aliases`, nombre de contradictions sur les concepts filtrés, `latest_status`, `confidence_hint` (heuristique MVP : importance + `access_count`).

Exemple :

`/memory/decision-trace?concept=DeepSeek&project=openchawn`

## Limites MVP

- Pas d’UI timeline : consommation JSON / futur front.
- `reconstructed_context_summary` est une **approximation** (ordre des événements, pas le prompt exact).
- `key_decisions` utilise des heuristiques sur le texte et les scores.
- Multi-workers : ordre global des timestamps peut se chevaucher ; le fichier est protégé par un verrou process-local.
- Railway : si le backend JSON est éphémère, la timeline l’est aussi (aligné sur le store mémoire actuel).

## Futur UI timeline

- Brancher un panneau « session » sur `GET /memory/replay/session/{id}`.
- Vue « concept » sur `GET /memory/decision-trace`.
- Basculer le append vers **Postgres** en conservant le même schéma logique d’événement.
