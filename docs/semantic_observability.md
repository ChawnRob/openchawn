# Semantic Observability (V11.6)

Mini guide d'observabilité pour la couche semantic hybride d'OpenChawn.

## Sources de signal

- Log structuré versionné:
  - clé: `semantic_health_event_v116`
  - payload JSON avec:
    - `schema`
    - `schema_version`
    - `at`
    - `query_len`
    - `project_slug`
    - `semantic_candidates`
    - `semantic_contributed`
    - `semantic_duplicates`
    - `semantic_hit_rate`
    - `fractal_before_semantic`
    - `result_total`
- Endpoint runtime:
  - `GET /memory/semantic/health?window=50`
  - agrégats récents (`avg_hit_rate`, `avg_candidates`, etc.)

## Exemple de log

```text
semantic_health_event_v116={"schema":"semantic_health_event_v116","schema_version":"1.0","at":"...","query_len":37,"project_slug":"openchawn","semantic_candidates":2,"semantic_contributed":0,"semantic_duplicates":2,"semantic_hit_rate":0.0,"fractal_before_semantic":3,"result_total":3}
```

## Interprétation rapide

- `semantic_hit_rate` bas + `semantic_duplicates` haut:
  - la couche fractale couvre déjà bien les besoins.
- `semantic_candidates` haut + `semantic_contributed` bas:
  - candidates semantic non exploitables (filtres, contradictions, dedup).
- `semantic_contributed` haut:
  - bonne valeur ajoutée de FAISS sur ce trafic.

## Railway (logs)

- Filtrer les logs contenant `semantic_health_event_v116=`.
- Dashboard minimal recommandé:
  - moyenne `semantic_hit_rate` (5m / 1h)
  - somme `semantic_contributed`
  - somme `semantic_duplicates`

## Datadog (parsing)

1. Créer un pipeline de parsing sur les logs applicatifs.
2. Matcher la clé `semantic_health_event_v116=`.
3. Extraire le JSON à droite du `=`.
4. Mapper les champs:
   - `semantic_hit_rate` (gauge)
   - `semantic_candidates` (count)
   - `semantic_contributed` (count)
   - `semantic_duplicates` (count)
   - `query_len` (distribution)
5. Ajouter tags:
   - `schema`
   - `schema_version`
   - `project_slug`

## Alertes minimales

- **Hit-rate anormalement bas**
  - condition: `avg(last_30m):semantic_hit_rate < 3`
  - utile pour détecter un drift ou un mauvais réglage des filtres.
- **Contribution nulle prolongée**
  - condition: `sum(last_1h):semantic_contributed == 0`
  - utile pour détecter un index vide ou un rebuild cassé.
- **Duplication excessive**
  - condition: `avg(last_30m):semantic_duplicates > avg(last_30m):semantic_candidates * 0.9`
  - utile pour ajuster `semantic_boost` / caps / policy.

## Checklist opérationnelle

- Vérifier `GET /memory/semantic/stats` après deploy.
- Vérifier `GET /memory/semantic/health` après traffic réel.
- Lancer `POST /memory/semantic/rebuild?incremental=true` en maintenance légère.
- Lancer `POST /memory/semantic/rebuild` (full) si drift confirmé.

