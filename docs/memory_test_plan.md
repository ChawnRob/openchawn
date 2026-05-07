# Plan de test — mémoire fractale V11.6

## Objectif

Valider en local (ou CI) que la mémoire fractale **écrit**, **retourne** des extraits pertinents, respecte l’**ordre des couches** dans le prompt, extrait le **concept DeepSeek**, applique le **renforcement** (`access_count`), expose **last-context** / **health** / **observabilité**, et **bloque** les contenus type clé API.

## Exécution

```bash
cd /chemin/vers/openchawn
.venv/bin/python scripts/test_memory_flow.py
```

Le script :

- force **`MEMORY_BACKEND=json`** (évite un backend Postgres vide en CI / Railway) ;
- redirige `fractal_memory.STORE_PATH` vers un **fichier JSON temporaire** ;
- utilise **FastAPI `TestClient`** (pas besoin de serveur HTTP séparé) ;
- reste **sans** base vectorielle ni embeddings.

## Cas couverts

| Étape | Vérification |
|--------|----------------|
| Write | Quatre écritures (system / **project** DeepSeek / user / session) ; la phrase projet évite le motif `provider principal` pour rester en `memory_type=project`. |
| Retrieval | La requête sur le provider OpenChawn remonte **DeepSeek** dans le texte de contexte. |
| Layering | Présence et ordre des blocs : **MÉMOIRE SYSTÈME** → **PRÉFÉRENCES UTILISATEUR** → **MÉMOIRE PROJET** → **CONTEXTE SESSION**. |
| Concept | Chaîne **« DeepSeek est provider principal »** dans `/memory/concepts/graph` ou `/memory/concepts`. |
| Reinforcement | Deux appels successifs au même retrieval augmentent `access_count` sur une entrée sélectionnée. |
| Last context | `/memory/last-context` contient `why_selected`, `relevance_score`, `importance_score`, `decay_score`. |
| Secret | Écriture refusée et chaîne `sk-test-secret` absente du JSON disque. |
| Health | `/health/memory`, `/health/memory/lifecycle`, `/memory/observability/overview` répondent OK. |

## Note sur la phrase « projet »

La formulation exacte *« OpenChawn utilise DeepSeek comme provider principal sur Railway »* déclenche la classification **system** (heuristique `provider principal` / `deepseek…principal`). Le script utilise une variante **projet** explicitement (voir source du script) tout en conservant le **concept canon** attendu.

## Futur (non couvert ici)

- UI timeline / graphe mémoire / explorateur sémantique.
