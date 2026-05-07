# Memory Reflection Engine V11.6

## Rôle

Observer les **instantanés légers** produits par le Memory Decision Engine (historique process-local, deque bornée) pour :

- repérer les mémoires souvent **sélectionnées** ou **rejetées** ;
- mesurer les **conflits récurrents** (signatures `(kind, memory_ids)` agrégées) ;
- estimer une **stabilité cognitive** heuristique sur une échelle **0–100** ;
- signaler des **projets instables** (densité de conflits par snapshot) ;
- suggérer des **optimisations** (réconciliation de mémoires, decay élevé, archives, providers).

Aucun LLM, embedding, base vectorielle ou agent autonome.

## Pipeline conceptuel (non forcé dans `/api/chat`)

```
Mémoire fractale
      ↓
Memory Decision Engine (arbitrage prompt)
      ↓
Historique décisionnel (instantanés « ok »)
      ↓
Memory Reflection Engine (ce module)
      ↓
(World Impact Layer — module séparé, endpoints dédiés)
      ↓
Réponse / action future
```

## Source de données

À chaque `set_last_decision_bundle` avec bundle `status=ok`, un instantané réduit est ajouté à une deque (voir `get_decision_history()` dans `memory_decision_engine.py`). Les chaînes exposées passent par `sanitize_timeline_text`.

## Endpoints

| Méthode | Route | Description |
|--------|-------|-------------|
| `GET` | `/memory/reflection/report` | Rapport agrégé : stabilité, motifs sélection/rejet, conflits répétés, projets instables, recommandations, résumé. |

## Limites MVP

- Historique **en mémoire process** : redémarrage Railway = perte de l’historique (extension Postgres prévue).
- Heuristiques lexicales / fréquentielles : pas de sémantique profonde.
- Pas de causalité prouvée entre stabilité score et qualité utilisateur.

## Futur

- **Semantic reflection layer** : regroupement de motifs par embedding ou graphe élargi (hors MVP).
- **ASI-evolve scoring** : boucle fermée avec métriques produit et simulations world-model (voir `docs/world_impact_layer.md`).
