# Retrieval Policy Layer V11.6

## Rôle

Étend le **Cognitive State Engine** avec des **règles déterministes** sur :

- quotas de retrieval par couche (`max_system` … `max_session`),
- niveau de **diversité** (élargissement projet multi-scope),
- mode **contradictions** (injection optionnelle de mémoires `contradiction_detected`),
- **compression** des clés de déduplication (summaries),
- **échelles** repassées au Memory Decision Engine (`conflict_penalty_scale`, `confidence_scale`) puis fusionnées avec les modificateurs « pression cognitive ».

Sans embeddings, FAISS, vector DB ni appel LLM.

## Pipeline

```
Cognitive State Engine (snapshot)
        ↓
build_retrieval_policy()
        ↓
gather_layered_candidates(... policy kwargs ...)
        ↓
Memory Decision Engine (arbitrage + caps fusionnés)
        ↓
Prompt final
```

## Endpoints

| Route | Description |
|-------|-------------|
| `GET /memory/retrieval-policy` | Dernière policy **appliquée** après un tour mémoire réel ; sinon reconstruction depuis le snapshot cognitif courant. |
| `GET /memory/retrieval-policy/simulate?state=focused` | Policy pure pour un état cognitif demandé (sans persister le dernier snapshot retrieval). |

## Limites MVP

- Heuristiques lexicales / quotas : pas de scoring sémantique profond.
- Diversité « exploring » = split projet local / multi-projets contrôlé par seuil sur `diversity_level`.
- Compatible extension future **FAISS** / Obsidian : interface policy reste un dict sérialisable.
