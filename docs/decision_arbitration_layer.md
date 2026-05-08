# Decision Arbitration Layer V11.6

## Role
La couche `decision_arbitration` arbitre entre plusieurs options avant action/reponse, sans appel LLM obligatoire.

Entrées principales:
- `importance_score`
- `graph_centrality`
- `temporal_status`
- `contradiction_resolution_status`
- `context_confidence`
- `context_risk`
- signaux provider/cost/stability

## Scores
Chaque option produit:
- `confidence_score`
- `risk_score`
- `stability_score`
- `cost_score`
- `temporal_score`
- `graph_score`
- `contradiction_penalty`
- `final_score`

## Statuts
- `selected`
- `rejected`
- `tie_needs_review`
- `blocked_by_risk`
- `no_viable_option`
- `needs_human_review`

Regles cles:
- `unresolved/conflict_active` penalise fortement;
- `needs_human_review` jamais auto-selected;
- `resolved/superseded` recent augmente la confiance;
- `rising/stable` augmente le score temporel;
- `deprecated/superseded` perd sauf mode debug;
- tie de score proche => revue humaine.

## Pipeline Decisionnel
1. `build_arbitration_options()`
2. `score_decision_option()`
3. `compare_decision_options()`
4. `arbitrate_decision()`
5. `build_arbitration_report()`

## Interaction avec Memory Decision Context
- `memory_decision_context.build_decision_context()` declenche l'arbitrage apres assemblage du contexte;
- les options sont derivees des memoires selectionnees et des signaux cross-layer;
- le resultat est expose dans `context["arbitration"]`.

## Interaction avec World Impact Layer
- `consequence_predictor.build_impact_report()` recupere `arbitration_selected_option` via `decision_context["arbitration"]["selected_option"]`.

## Endpoints
- `GET /decision/arbitration/last`
- `POST /decision/arbitration/simulate`
- `GET /decision/arbitration/report`
- `GET /decision/arbitration/explain/{option_id}`

## Limites MVP
- heuristiques statiques;
- pas d'optimisation multi-objective globale;
- pas d'apprentissage automatique des poids par environnement.

## Futur
- ASI-evolve arbitration feedback loops;
- human-in-the-loop workflows avec validation explicite;
- optimisation multi-objective cout/risque/stabilite/confiance.

