# Index logique — carte des connaissances (mémoire fractale V11.6)

## Objectif

Offrir une **vue tabulaire / graphe léger** des concepts dérivée uniquement du store JSON mémoire : pas d’embedding, pas d’LLM, pas de base vectorielle — uniquement agrégats, degrés, heuristiques de statut et « gravité » par projet (aligné Railway / futur Postgres).

## Endpoints

| Méthode | Route | Description |
|---------|-------|--------------|
| `GET` | `/memory/index` | Index complet : concepts annotés (`centrality_score`, `influence_score`, …) + liste `projects_gravity` |
| `GET` | `/memory/concepts/top` | Query `limit` (1–80) : concepts triés par centralité puis influence |
| `GET` | `/memory/graph/stats` | Métriques globales du graphe concept ↔ mémoires liées |
| `GET` | `/memory/projects/gravity` | Tableau gravité par `project_name` |

Les réponses d’erreur backend mémoire reprennent `status: "error"` avec `config_error` (sans secrets).

## Métriques (MVP)

- **concept_id**, **canonical_summary** (résumé nettoyé via la même passe que la timeline contre les motifs type clés API), **aliases**
- **linked_memories_count** : arêtes sortantes vers summaries / raw / enfants métier connus depuis le fichier
- **linked_projects** : slugs projet vus sur le concept et les mémoires liées
- **memory_types** : types présents parmi les mémoires liées (plus le type du concept)
- **merge_count** : champ `metadata.merge_count` canonique fractal (≥ 1)
- **contradiction_count** : drapeaux + nombre de liaisons antagonistes même sujet (heuristique `apply_provider_*` existante)
- **centrality_score** (0–100) : pseudo centralité weighted-degree entre voisinage + merges + tensions signalées
- **influence_score** (0–100) : mélange importances, usages (`access_count` agrégés), dispersion par projets, centralité locale
- **decay_pressure** : pression vieillissement amortie par merges (pour la lecture « fading » sans scheduler)
- **status** parmi :
  - `hot` — en tête de cohorte centralité + influence relatives
  - `stable`
  - `fading` — forte pression de decay + centralité relative basse (actifs seulement)
  - `contradicted`
  - `archived`

**Gravité projet** (`projects_gravity`) : pour chaque slug — totaux/actifs mémoires, `top_concepts`, `average_importance`, `average_decay`, `contradiction_count`, **`gravity_score`** (composite heuristique, pénalise contradiction et décay trop haut sans masse cognitive).

Réponse additionnelle sur `/memory/index` : **`hot_concepts`**, **`dying_concepts_watchlist`** (IDs à surveiller côté produit/outillage).

## Limites MVP

- Pas de synonymie sémantique : deux libellés distincts donnent deux nœuds.
- Centralité graphe-limitée aux liens mémoires explicites (IDs + `linked_concept_id`), pas les relations NLP.
- Comparaisons inter-projets peuvent compter plusieurs fois une même contradiction si plusieurs entrées d’un même projet sont marquées flag.
- Perf : recomputation complète à chaque requête (acceptable pour quelques milliers de mémoires), à matérialiser en Postgres ensuite.

## Futur semantic layer

- Pondération PMI ou co-occurrence embeddings stockés hors hot path inference.
- Pré-calcul nightly des scores + versioning d’index.
- Jointure timeline (`/memory/replay`) pour tracer *pourquoi* un concept monte dans `hot_concepts`.
