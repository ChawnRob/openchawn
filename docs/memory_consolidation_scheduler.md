# Memory Consolidation Scheduler (V11.6)

## Rôle

Le **Memory Consolidation Scheduler** joue un rôle analogue à un **sommeil cognitif léger** pour la mémoire fractale : il regroupe une maintenance **locale et déterministe** (compression, archivage par règles, décay, fusion « safe » de concepts en doublon) **hors du flux synchrone `/chat`**, afin de ne pas ralentir ni désynchroniser les réponses utilisateur.

- **Pas d’appels LLM**, pas d’embeddings, pas de base vectorielle, pas d’agent autonome.
- **Pas de suppression** des entrées mémoire sources : uniquement archivage (lifecycle), compression (nouvelles entrées agrégées + métadonnées sur les sources), et coalescence de concepts par archivage ciblé.
- Les secrets / tokens décrits par les garde-fous existants (`_contains_sensitive_text`, flags metadata) sont **explicitement exclus** des candidats fusion / compression applicables par ce module.

## Endpoints FastAPI

| Méthode | Chemin | Description |
|--------|--------|-------------|
| `GET` | `/memory/consolidation/plan` | Plan consolidation : seuils heuristiques, pressions mémoires / doublons / contradictions, comptes candidats, notes de sécurité. |
| `POST` | `/memory/consolidation/run-light` | Exécute un **cycle léger** (compression légère, règles d’archive, refresh decay, coalesce concepts safe, rapport court). |
| `POST` | `/memory/consolidation/run-deep` | Consolidation **profonde** réservée à un **appel explicite** (voir ci-dessous). |
| `GET` | `/memory/consolidation/last-report` | Dernière synthèse de cycle (clair / profond ou `idle`). |

## Light vs Deep consolidation

### Light (`run-light`)

Déclenchée **réactivement ou manuellement** via l’endpoint (le plan `GET …/plan` indique si un cycle serait pertinent, mais `run-light` exécute toujours une passe de maintenance lorsqu’elle est appelée).

Signaux qui alimentent le **plan** (non exhaustif) :

- forte pression doublons / buckets de compression,
- pression « mémoire » (lifecycle, decay, santé),
- surcharge cognitive snapshot (`overloaded`, score de pression),
- backlog de candidats archive / clusters de compression,

### Deep (`run-deep`, V11.6)

La consolidation **profonde** **n’est jamais lancée automatiquement** par le scheduler V11.6 : elle requiert un `POST` explicite. Elle applique une variante plus large de coalesce, un scan contradiction (récap), puis enchaîne (sans LLM dans ce module) des rapports de **réflexion** et **impact monde** déjà disponibles dans le codebase, ainsi qu’un **rebuild d’index** mémoire.

## Indication côté `/chat`

Une réponse de chat peut inclure `consolidation_recommended: true` lorsque `build_consolidation_plan()` estime utile une consolidation **légère**. **Aucune consolidation** n’est exécutée pendant la traitement du message (`/chat` reste léger et compatible comportement précédent, avec ce champ JSON supplémentaire).

## Pourquoi avant FAISS ou autre recherche dense

Ce scheduler reste dans le plan **qualitatif + structurel** (JSON fractal, règles de lifecycle et de compression locales). Introduire FAISS / embeddings élève le coût, la confidentialité et l’infra ; la consolidation V11.6 **nettoie et compresse les artefacts textuels** déjà présents pour que :

- les futurs backends (PostgreSQL unifié) manipulent **moins de lignes triviales répétées**,
- les politiques de récupération (retrieval policy) lisent une mémoire **moins fragmentée**.

## Railway, Postgres, travail hors requête

- **Railway / conteneurs** : les endpoints peuvent être appelés par un cron interne Railway ou un worker séparé quand vous le brancherez (hors périmètre V11.6).
- **Postgres futur** : la logique de planification reste orthogonal au stockage (lecture liste d’entrées + écritures filtrées comme aujourd’hui sur JSON).

## Scripts de test

```bash
cd openchawn && .venv/bin/python scripts/test_memory_consolidation_scheduler.py
```

Voir aussi `scripts/test_memory_compression.py` pour la couche compression seule.
