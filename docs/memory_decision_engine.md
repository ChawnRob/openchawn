# Memory Decision Engine V11.6

## Pipeline cible

```
Memory Retrieval (couches fractales)
        ↓
Candidate Scoring (heuristique locale)
        ↓
Conflict Detection (polarités / flags / vocabulaire sensible)
        ↓
Context Arbitration (quotas par memory_type + tie-break)
        ↓
Final Prompt Assembly (texte injecté dans /api/chat)
```

Le module `app/memory/memory_decision_engine.py` est **sans appel LLM**, sans embeddings ni base vectorielle — uniquement scores dérivés du JSON mémoire et du graphe concept léger (`memory_index`).

## Scoring (MVP)

Pour chaque candidat issu du retrieval annoté (`_retrieval_debug`) :

| Champ | Rôle |
|--------|------|
| `relevance_score` | Chevauchement lexical query ↔ mémoire (comme retrieval existant) |
| `importance_score` | Champ fractal 0–1 |
| `decay_score` | Pénalité vieillissement (0–100) |
| `centrality_score` / `influence_score` | Lookup concept lié (`linked_concept_id`) via `concept_centrality_influence_maps` |
| `contradiction_penalty` | Flag `contradiction_detected` + surcoûts paires en conflit |
| `recency_score` | Bonus récence monotonique |
| **`final_decision_score`** | `relevance_term + importance_term + centrality + influence + recency − decay − contradiction_penalty` |

Les termes intermédiaires sont détaillés dans `scoring_breakdown` renvoyé par `/memory/decision/simulate`.

## Conflits

Détection non résolutive — uniquement **pénalités** et mentions dans `_decision_debug` :

- même sujet lexical (`_concept_sentiment_signals`) avec polarités opposées ;
- double `contradiction_detected` avec vocabulaire provider/production commun ;
- tensions croisées DeepSeek/Ollama avec indices prod/interdit/principal.

## Arbitrage

Quotas stricts :

- max **2** `system`, **2** `user`, **3** `project`, **5** `session`

Tri global par `final_decision_score` décroissant, puis **récent** (`timestamp`). Les mémoires archivées ou inactives sont **écartées avant scoring visible**.

## `_decision_debug` (mémoires sélectionnées ou rejetées)

```json
{
  "selected": true,
  "final_decision_score": 123.4,
  "reasons": ["layer:project", "..."],
  "penalties": ["pairwise_conflict_penalty=22", "..."],
  "conflicts": [{"kind": "...", "detail": "..."}],
  "arbitration_rank": 1
}
```

Les résumés et chaînes exposées via API passent par `sanitize_timeline_text` pour éviter fuites de secrets.

## Endpoints

Les instantanés « ok » sont également conservés dans une **deque bornée** (`get_decision_history()`) pour le **Memory Reflection Engine** (`/memory/reflection/report`).

| Route | Description |
|-------|-------------|
| `GET /memory/decision/last` | Dernier bundle produit par un passage réel retrieval→décision (ex. dernier `/api/chat` ayant chargé la mémoire). Payload « lean » (pas de `user_message` brut). |
| `GET /memory/decision/simulate?query=&project=&user_key=&as_guest=` | Simulation **read-only** : recalcul decay sur copie mémoire **sans persister** ; **ne met pas à jour** `last` pour ne pas écraser la trace du dernier chat réel. |

## Intégration `/api/chat`

`build_layered_memory_context` enchaîne désormais :

`gather_layered_candidates` → `build_memory_decision_bundle` → timeline `memory_retrieved` **sur sélection** → `reinforce_entries` **sur sélection** → assembly du bloc texte arbitré.

## Limites MVP

- Pas de résolution sémantique fine des conflits (choix par score + quotas).
- Centralité/influence dépendent du graphe concept tel que construit dans `memory_index`.
- Simuler deux appels successifs ne reflète pas `last` le plus récent chat si le second est simulate-only.

## Futur semantic decision layer

- Couche de scores PMI / co-occurrence ou embeddings **hors hot path** avec table Postgres matérialisée.
- Politiques métier versionnées par projet (`policy_id` dans `_decision_debug`).
