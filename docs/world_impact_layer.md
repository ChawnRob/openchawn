# World Impact Layer (préparation MVP)

## Rôle

Ébaucher une couche **« conséquences probables »** pour une action proposée, **sans appeler de LLM**, sans JEPA ni world model neuronal. Les sorties sont des **listes heuristiques** et des **étiquettes d’impact** (technique, coût, stabilité, sécurité, provider, mémoire).

Elle complète conceptuellement :

`Memory → Decision Engine → Reflection Engine → World Impact → décision humaine ou orchestration future`.

## Module

- `app/decision/consequence_predictor.py`
  - `predict_action_consequences()`
  - `score_risk_benefit()`
  - `build_impact_report()` — persiste le dernier rapport en mémoire process (`get_last_impact_report()`).

Les entrées peuvent inclure un `decision_context` minimal (ex. dernier bundle décision : nombre de conflits). Aucune clé API ni secret ne doit être renvoyé : préfixes suspects sont neutralisés via `sanitize_timeline_text`.

## Endpoints

| Méthode | Route | Description |
|--------|-------|-------------|
| `POST` | `/decision/predict-consequences` | Corps JSON `{ "proposed_action": "...", "project": "openchawn" }`. Retourne bénéfices/risques et impacts par axe + `confidence_hint`. |
| `GET` | `/decision/last-impact` | Dernier rapport produit par `predict-consequences` dans ce processus ; placeholder vide si aucune prédiction. |

## Limites MVP

- Règles **mot-clé** (PostgreSQL, Railway, providers, cache, auth…) — faux positifs/négatifs possibles.
- Pas de simulation temporelle ni de graphe de dépendances services.
- État **volatile** : dernier impact non persisté en base.

## Futur JEPA / world model

- Encoder état environnement (infra, versions, charge) et actions dans un esprit **world model** pour rollouts courts.
- Calibration via données réelles (post-mortems, incidents, métriques Railway).

## Futur ASI-evolve scoring

- Joindre réflexion mémoire + impact prédit + résultats observés pour ajuster poids heuristiques ou policies (hors scope MVP).
