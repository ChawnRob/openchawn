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
1. `GET /health`
2. `GET /health/providers`
3. `GET /health/language`
4. `GET /memory/semantic/health`
5. `GET /memory/semantic/stats`
6. `GET /memory/importance/health`
7. `GET /memory/importance/top`
8. `GET /memory/graph/stats`
9. `GET /memory/graph/hubs`
10. `GET /memory/temporal/snapshot`
11. `GET /memory/temporal/rising`
12. `GET /memory/contradictions/report`
13. `GET /decision/arbitration/report`
14. `GET /decision/arbitration/last`
15. `POST /decision/arbitration/simulate`
16. `POST /api/chat`

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

