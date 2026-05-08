# Memory Decision Context Layer V11.6

## Architecture Cognitive
Le layer `memory_decision_context` construit un contexte cognitif avant toute decision/reponse en combinant:
- importance des memoires;
- signaux graphe (hubs, clusters, centralite);
- signaux temporels (rising/stale/momentum);
- etat des contradictions (resolved/unresolved/human review).

Sortie principale:
- `selected_memories`
- `dominant_concepts`
- `active_clusters`
- `unresolved_conflicts`
- `temporal_trends`
- `stable_decisions`
- `context_confidence`
- `context_stability`
- `context_risk`
- `fragmentation_score`
- `reasoning_summary`

## Pipeline Decisionnel
1. selection heuristique des memoires pertinentes (`importance + centrality + trend + recurrence`);
2. penalisation `deprecated/unresolved/conflict_active`;
3. construction de clusters actifs;
4. injection des signaux temporal/graph/contradiction;
5. calcul confiance/stabilite/risque/fragmentation;
6. consommation par `memory_decision_engine`.

## Scoring
- confiance: baisse avec conflits non resolus, stale decisions et fragmentation;
- stabilite: augmente avec rising concepts, baisse avec stale/unresolved;
- risque: augmente avec conflits actifs et besoins de revue humaine.

## Fragmentation
`fragmentation_score` estime la dispersion contextuelle:
- nombre de clusters actifs vs volume de memoires selectionnees;
- penalite si aucun cluster dominant.

## Interaction Cross-Layer
- Retrieval: ajoute `context_weight`, `context_priority`, `context_decision_relevance`.
- Graph: ajoute `dominant_concepts` et `active_clusters`.
- Temporal: ajoute `rising_concepts`, `stale_decisions`, momentum.
- Contradiction: ajoute conflits non resolus + confiance de resolution + `human_review_required`.
- Decision Engine: lit `build_decision_context()` avant arbitrage final.
- Compression: protege concepts dominants et decisions stables.
- FAISS: boost des memoires de clusters dominants.

## Endpoints
- `GET /memory/context/build`
- `GET /memory/context/explain`
- `GET /memory/context/risk`
- `GET /memory/context/stability`
- `GET /memory/context/clusters`

## Limites MVP
- heuristiques deterministes, sans LLM;
- pas de planification contextuelle multi-objectif;
- pas d'apprentissage adaptatif de poids par utilisateur.

## Futur
- context planner (strategies dynamiques par intention);
- integration world-model pour coherence globale;
- pondération emotionnelle QEI sur priorisation contextuelle.

