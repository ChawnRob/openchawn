# FAISS Semantic Retrieval Layer V11.6

## Rôle

La couche `FAISS` enrichit le retrieval mémoire d'OpenChawn avec une recherche sémantique locale.
Elle est **complémentaire** :

- le pipeline fractal/timeline reste la source principale de contexte,
- la couche semantic ajoute des candidats pertinents non captés par simple overlap lexical,
- aucun contrat HTTP de `/chat` n'est modifié.

## Architecture hybride (obligatoire)

Flux de retrieval dans `build_layered_memory_context` :

1. récupération fractale/timeline (system, user, project, session, compressed),
2. application de la retrieval policy (contradiction mode, caps, cognitive state),
3. ajout semantic via `faiss_memory.semantic_candidates_for_query`,
4. fusion finale avec dedup stricte (id + summary normalisée).

La couche semantic n'écrase jamais les couches natives ; elle ne fait qu'ajouter un signal.

## Composants

- `app/memory/embedding_provider.py`
  - `embed_text`, `embed_batch`
  - priorité à `sentence-transformers` local,
  - fallback hash embedding déterministe (tests/offline).
- `app/memory/faiss_memory.py`
  - `build_faiss_index`
  - `add_memory_embedding`
  - `search_semantic_memory`
  - `rebuild_semantic_index`
  - `remove_memory_embedding`
  - `semantic_candidates_for_query`
  - `get_semantic_index_stats`

## Persistance et sécurité

- index stocké localement sous `data/memory/semantic/`,
- mapping `vector_id -> memory_id` persisté dans `faiss_meta.json`,
- lock thread-safe pour build/add/remove/search/rebuild,
- filtres metadata supportés :
  - `project_name`
  - `memory_type`
  - `language`
  - `archived`
  - `contradicted`
- entrées sensibles ignorées à l'indexation (pas de secret dans payload semantic).

## Multilingue

Le provider d'embedding est local et multilingue (quand sentence-transformers est disponible).
Le fallback hash garde des ponts lexicaux minimaux FR/EN/ES/PT pour les tests.
Objectif produit : ne jamais imposer l'anglais.

## Pourquoi FAISS ne remplace pas la mémoire fractale

FAISS optimise la similarité vectorielle mais ne porte pas à lui seul :

- le cycle de vie mémoire (decay/archive),
- la cohérence temporelle timeline,
- les règles contradictoires/policy/cognitive state.

La mémoire fractale garde la gouvernance ; FAISS fournit un boost de rappel sémantique.

## Semantic drift

Risque : des voisins vectoriels peuvent devenir moins pertinents dans le temps.
Mitigations V11.6 :

- rebuild complet disponible (`POST /memory/semantic/rebuild`),
- filtres metadata + exclusion contradictions/archives selon policy,
- hybrid fusion + dedup stricte.

## Endpoints

- `GET /memory/semantic/search?q=...`
- `GET /memory/semantic/stats`
- `POST /memory/semantic/rebuild`

## Futur Obsidian / Notion

Le mapping `vector_id -> memory_id` prépare un pont futur vers des nœuds externes
(Obsidian/Notion) : on peut indexer des snapshots textuels externes sans casser
la gouvernance fractale interne.

