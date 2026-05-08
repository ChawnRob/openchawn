# Cognitive State Engine V11.6

## Rôle

Agréger des **signaux locaux** issus de :

- Memory Reflection / Decision (historique snapshots, dernier bundle),
- lifecycle mémoire (`memory_lifecycle_health`),
- graphe conceptuel (`graph_statistics`, concepts « hot » via `top_concepts_response`),
- hooks santé providers (`provider_health_hooks.snapshot()`),
- ampleur du retrieval (`nombre de candidats` avant arbitrage).

Produit un **état cognitif** labelisé, un **score de pression 0–100**, et des **modificateurs légers** pour :

- réduire les quotas session/projet arbitrés sous forte pression,
- augmenter légèrement les **pénalités de conflit** dans le Decision Engine,
- ajuster le **`confidence_hint`** du bundle mémoire,
- ajouter une **phrase optionnelle** dans le prompt `/api/chat` lorsque la confiance contexte n’est pas « high ».

## États possibles (un primaire)

`stable`, `focused`, `exploring`, `contradicted`, `overloaded`, `uncertain`, `high_confidence`, `memory_fragmented`.

Choix **heuristique déterministe** selon pression, contradictions, santé mémoire, largeur retrieval, stabilité provider, dispersion projets.

## Endpoints

| Route | Description |
|-------|-------------|
| `GET /cognition/state` | Snapshot public (champs listés ci‑dessous). |
| `GET /cognition/pressure` | Même payload — utile pour dashboards ciblés pression. |
| `GET /cognition/focus` | Même payload — utile pour projet/concepts dominants. |

Champs retournés : `status`, `state`, `pressure_score`, `primary_project`, `primary_concepts`, `contradiction_level`, `provider_stability`, `retrieval_health`, `memory_health`, `confidence_level`.

## Intégration pipeline

1. `build_layered_memory_context` calcule les modificateurs avec **`memory_modifiers_for_retrieval_pass(..., entries=entries)`** sous le verrou fractal : les métriques lifecycle/graphe sont dérivées des entrées **déjà chargées**, sans second acquire `_STORE_LOCK` (évite deadlock).
2. Après sauvegarde store / timeline, `record_post_turn_snapshot` met à jour le dernier état cognitif pour les endpoints et le chat suivant (wording confiance).

## Limites MVP

- État **volatile** (process memory), comme Reflection/Decision.
- Pas de modèle du monde ni embeddings ; pas de LLM dans cette couche.
- Signaux « provider » dépendent des compteurs succès/échec hooks (pas une sonde réseau complète).

## Futur

- Persistance Postgres des snapshots + courbes temporelles.
- Calibration des seuils par projet (`policy_id`).
- Liaison ASI-evolve / métriques produit pour ajuster les pondérations.
