# Memory Relationship Graph Layer V11.6

## Rôle

Transformer les mémoires isolées en graphe relationnel cognitif, exploitable par:

- retrieval,
- consolidation,
- contradiction analysis,
- decision engine.

## Architecture du graphe

- `app/memory/memory_relationship_graph.py`
  - `build_memory_relationship_graph`
  - `link_related_memories`
  - `compute_relationship_strength`
  - `extract_memory_concepts`
  - `find_related_memories`
  - `detect_memory_clusters`
  - `detect_concept_hubs`
  - `explain_memory_relationships`
  - `refresh_relationship_graph`
- `app/memory/graph_persistence.py`
  - `save_relationship_graph`
  - `load_relationship_graph`
  - `rebuild_relationship_graph`
  - `graph_stats`

Persistance locale:

- `data/memory/relationship_graph/graph_snapshot.json`

## Types de relation

- `semantic_similarity`
- `shared_project`
- `provider_strategy`
- `contradiction` (poids négatif)
- `chronology`
- `architecture_dependency`
- `repeated_decision`
- `causal_relation`
- `consolidation_relation`

## Centrality et clusters

- `graph_degree`: nombre de voisins liés.
- `graph_centrality`: somme pondérée des forces absolues.
- `cluster_id`: composantes connectées (seuil relation forte).
- `detect_concept_hubs`: top noeuds centraux.

## Interaction avec FAISS

- les signaux semantic/retrieval hits enrichissent les concepts extraits.
- `semantic_match_hits` (quand disponible) aide la sémantique relationnelle.
- FAISS reste complémentaire, le graphe n’écrase pas le pipeline fractal.

## Interaction avec importance scoring

- `memory_importance` intègre `graph_degree` + `graph_centrality` dans `long_term_value`.
- les mémoires centrales tendent à remonter en importance.

## Intégration retrieval/consolidation/decision

- retrieval ranking ajoute un boost centralité (`graph_centrality`).
- consolidation prend en compte les clusters stables (`stable_clusters`).
- decision engine peut expliquer: mémoire liée à X/Y/Z.

## Endpoints

- `GET /memory/graph/stats`
- `GET /memory/graph/hubs`
- `GET /memory/graph/related/{memory_id}`
- `POST /memory/graph/rebuild`
- `GET /memory/graph/explain/{memory_id}`

## Limites MVP

- pondérations heuristiques statiques.
- pas de raisonnement multi-hop avancé.
- clustering simple basé sur composantes connectées.

## Futur

- backend Neo4j/GraphDB optionnel.
- traversal orienté reasoning multi-hop.
- world-model integration.
- support Postgres graph materialization.

