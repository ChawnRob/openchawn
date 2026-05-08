# Memory Compression + Summarization Layer (V11.6)

## Rôle

Réduire le bruit retrieval en **regroupant plusieurs souvenirs proches** en une entrée `memory_type="compressed"`, **sans LLM**, sans embeddings et sans base vectorielle.

- Les **sources restent sur disque** ; elles reçoivent `metadata.compressed_into` et une **baisse d’importance** pour limiter leur injection alors que la trace brute reste consultable (`/memory/trace/{id}`).
- Préparer une future couche **FAISS / export Obsidian** : une mémoire compressée porte un résumé structuré (`stable_facts`, `key_decisions`, `open_questions`) réutilisable par un summariseur futur ou un index hors runtime.

## Endpoints HTTP

| Méthode | Chemin | Description |
|--------|--------|-------------|
| `GET` | `/memory/compression/candidates` | Clusters potentiels (`include_archived` optionnel). |
| `POST` | `/memory/compression/run` | Lance la compression (`dry_run`, `include_archived`, `project` optionnels). |
| `GET` | `/memory/compression/health` | Compte compressées, clusters estimés, pression doublons par projet. |
| `GET` | `/memory/compression/{compressed_id}` | Détail d’une entrée `compressed` (champs projet + métadonnées). |

Secrets / tokens **ne sont jamais** résumés : toute ligne détectée par les heuristiques sensibles fractal ou un flag `metadata` de secret exclut l’entrée du cluster.

## Logique MVP (heuristiques)

1. **Éligibilité** : niveaux `summary_memory` ou `concept_memory`, pas `contradiction_detected`, pas archivées (sauf `include_archived`), pas déjà reliées à une compressée (`metadata.compressed_into`), pas sensible.
2. **Clé de cluster** : `project_name` normalisé, `memory_type`, `concept_id` (`metadata.linked_concept_id`), tags triés, **bucket canonique** = `concept_merge_key(summary)` (proxy de « summaries proches » sans embedding).
3. **Seuil** : taille minimale du cluster (**3** par défaut).
4. **Synthèse** : concaténations et motifs locaux (`?`, langage décisionnel) → `compressed_summary`, `key_decisions`, `stable_facts`, `open_questions`.
5. **Contradiction refs** : identifiants d’entrées **marquées contradictoires** partageant la même enveloppe projet/type/concept/tags (sans exiger le même canon) ; elles restent hors cluster.
6. **Marquage sources** : `compressed_into`, `importance_score *= ~0.32` (floor 0.02), `decay_score` recalculé.

Compat **Railway** : JSON local ou futur Postgres — champs riches stockés dans `metadata` comme le reste du store fractal.

## Intégration retrieval

Les entrées **`compressed`** sont injectées dans la couche projet via **`gather_layered_candidates`** lorsque la **Retrieval Policy** signale surcharge (`compression_level` agressif, état cognitif `overloaded`, ou forte pression de doublons sur le projet).

## Limites MVP

- Pas de réécriture sémantique : les amalgames suivent une **fusion textuelle**.
- Proximité = **concept_merge_key** identique → pas encore de fenêtre douce multi-clés fusionnées.
- Pas de résolution automatique des contradictions (seule exclusion + références).

## Futur summariseur contrôlé

Une passe LLM pourrait reformuler une **mémoire compressée** après validation gardes-fous (filtre secret sortie, quotas, versioning `metadata.compressor_revision`), en restant désactivée par défaut.

## Futur FAISS / Obsidian

- Réutiliser `source_memory_ids` pour lier vecteurs ou pages markdown.
- `compression_score` + `stable_facts` comme texte canonique stable pour indexer ou exporter sans dupliquer le bruit des bruts compressés.
