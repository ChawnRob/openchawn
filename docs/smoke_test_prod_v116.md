# Smoke Test Pack Production V11.6

## Role
Ce smoke test valide rapidement qu'une prod OpenChawn (Railway) est saine apres deploiement V11.6.

Le script execute des checks HTTP reels avec timeout court et classe chaque endpoint:
- `GREEN`: endpoint sain;
- `WARNING`: endpoint sain mais vide/non critique;
- `FAILED`: erreur HTTP, timeout, exception, JSON invalide attendu.

## Commandes
- `python scripts/smoke_test_prod_v116.py`
- `python scripts/smoke_test_prod_v116.py --base-url https://www.openchawn.com`
- `python scripts/smoke_test_prod_v116.py --json`
- `python scripts/smoke_test_prod_v116.py --fail-fast`

## Variable d'environnement
- `OPENCHAWN_PROD_URL` (optionnelle)
- fallback automatique: `https://www.openchawn.com`

## Endpoints testés
1. `POST /guest/session` (prépare le header `X-Guest-Session` pour `/chat`)
2. `GET /health`
3. `GET /health/providers`
4. `GET /health/language`
5. `GET /memory/semantic/health`
6. `GET /memory/semantic/stats`
7. `GET /memory/importance/health`
8. `GET /memory/importance/top`
9. `GET /memory/graph/stats`
10. `GET /memory/graph/hubs`
11. `GET /memory/temporal/snapshot`
12. `GET /memory/temporal/rising`
13. `GET /memory/contradictions/report`
14. `GET /decision/arbitration/report`
15. `GET /decision/arbitration/last`
16. `POST /decision/arbitration/simulate`
17. `POST /health/language/chat-dry-run` (assemblage prompt sans LLM; profil `fluxorca` attendu)
18. `POST /chat` (corps aligné sur l’UI: `project_name`, session invité)

## Sortie et résumé
Exemples:
- `[GREEN] GET /health 200 123ms ok`
- `[WARNING] GET /decision/arbitration/last 200 110ms empty_last_arbitration`
- `[FAILED] GET /memory/graph/stats None 10001ms timeout`

Résumé final:
- `total`
- `green`
- `warnings`
- `failed`
- `prod_green`
- `slowest_endpoint`
- `average_latency_ms`

## Sécurité logs
- pas d'affichage de secrets/env sensibles;
- redaction automatique des motifs token/api key/secret.

## Usage recommandé
Lancer ce smoke test apres chaque deploy Railway:
1. deploiement termine;
2. smoke test;
3. validation `prod_green=true` avant annonce.

## Futur
- exécution automatique GitHub Actions;
- post-deploy check Railway;
- gate de release conditionné au résultat smoke.

