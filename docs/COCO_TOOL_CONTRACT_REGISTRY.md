# COCO Tool Contract Registry — Specification

**Repo:** OpenChawn (COCO)  
**Branch cible doc:** `sandbox/staging-v11-7`  
**Statut:** documentation uniquement — **aucune implémentation runtime**  
**Parent:** `docs/COCO_AGENTIC_ORCHESTRATION.md`  
**Dernière révision doc:** 2026-06-03

---

## Purpose

Ce document définit le **standard ToolContract** et le **registre conceptuel** des outils COCO/OpenChawn. Chaque capacité actionnable est un contrat versionné, validé par le runtime, soumis à HITL si nécessaire, et journalisé si requis.

**Principe :** *Every tool is a contract.* — voir compartiment B dans `COCO_AGENTIC_ORCHESTRATION.md`.

---

## 1. Standard ToolContract

### 1.1 Champs obligatoires

Tout outil enregistré **doit** déclarer les champs suivants. Aucun champ optionnel pour la v1 spec — extensions via `metadata` documentées.

| Champ | Type | Description |
|-------|------|-------------|
| `name` | `string` | Identifiant stable, `snake_case`, unique dans le registre |
| `description` | `string` | Intention humaine + limites (ce que l’outil ne fait pas) |
| `version` | `string` | Semver du contrat (`1.0.0`) — bump si schéma ou HITL change |
| `category` | `enum` | Voir section 2 |
| `input_schema` | `object` | JSON Schema Draft 2020-12 (ou sous-ensemble documenté) |
| `output_schema` | `object` | Forme succès ; erreurs via enveloppe standard (§1.3) |
| `failure_modes` | `string[]` | Codes explicites issus du catalogue §3 |
| `requires_human_approval` | `boolean` | `true` si exécution bloquée jusqu’à HITL |
| `side_effect_level` | `enum` | `none` \| `read` \| `write` \| `external` |
| `timeout_ms` | `integer` | Plafond d’exécution (hard cancel côté runtime) |
| `retry_policy` | `object` | Voir §1.2 |
| `audit_log_required` | `boolean` | Si `true`, chaque invocation produit une trace persistée |

### 1.2 `retry_policy`

```json
{
  "mode": "none",
  "max_attempts": 1,
  "backoff_ms": 0,
  "idempotency_key_required": false
}
```

| `mode` | Usage |
|--------|--------|
| `none` | Aucun retry (défaut pour `write` / `external`) |
| `idempotent_only` | Retry uniquement si `idempotency_key` fourni et opération déclarée idempotente |
| `with_backoff` | Retry lecture / health check ; `max_attempts` ≤ 3 recommandé |

**Règle :** `side_effect_level` ∈ {`write`, `external`} ⇒ `retry_policy.mode` = `none` sauf exception auditée.

### 1.3 Enveloppe de réponse (runtime cible)

Succès :

```json
{
  "ok": true,
  "tool": "calculate_daily_cash",
  "version": "1.0.0",
  "result": { },
  "audit_id": "aud_01H…",
  "duration_ms": 142
}
```

Échec :

```json
{
  "ok": false,
  "tool": "import_restaurant_csv",
  "version": "1.0.0",
  "failure_mode": "invalid_input",
  "message": "human-readable summary",
  "details": { },
  "audit_id": "aud_01H…",
  "retryable": false
}
```

### 1.4 Règles de cohérence (validateur registre)

| Règle | Contrainte |
|-------|------------|
| R1 | `side_effect_level: external` ⇒ `requires_human_approval: true` |
| R2 | `side_effect_level: write` ⇒ `requires_human_approval: true` (sauf whitelist §4.3) |
| R3 | `audit_log_required: true` pour toute catégorie `admin_devops` et tout tool `external` |
| R4 | `failure_modes` doit inclure au minimum les codes applicables du catalogue §3 |
| R5 | `timeout_ms` ≥ 1000 ; plafond global registre : 120_000 ms (2 min) sauf dérogation documentée |
| R6 | `name` immuable ; évolution breaking ⇒ nouveau `version` ou nouveau `name` suffixé `_v2` |

### 1.5 Registre (conceptuel)

```text
RegistryEntry {
  contract: ToolContract
  status: draft | staging | active | deprecated
  owner_agent: string | null      # ex. "Restaurant Finance Agent"
  implemented: false              # toujours false jusqu'à GO code explicite
  mcp_exportable: boolean         # false par défaut
}
```

**État actuel :** registre **documentaire** — pas de fichier JSON/YAML généré en repo tant qu’un GO implémentation n’est pas donné.

---

## 2. Catégories d’outils

Chaque `ToolContract.category` appartient à **exactement une** catégorie.

| `category` | Périmètre | `side_effect_level` typique | HITL typique |
|------------|----------|----------------------------|--------------|
| `memory` | Retrieval, consolidation hints, trace read | `read` / `none` | non |
| `data` | Import, validation, preview datasets | `read` / `write` | write → oui |
| `restaurant_analytics` | Caisse, TVA, charges, KPIs | `read` | non |
| `supplier` | Alternatives, ruptures, comparaisons | `none` / `read` | non (commande = autre tool) |
| `promotion` | Scénarios marge, calendrier promo | `none` / `read` | non (publication = HITL) |
| `communication` | Brouillons, envoi messages | `none` / `external` | envoi → oui |
| `affine_workspace` | Notes, liens second brain | `external` | oui |
| `admin_devops` | Health providers, deploy hints | `read` / `external` | external → oui |

**Séparation des responsabilités :** un outil ne mélange pas deux catégories. Si un flux nécessite import + analytics, ce sont **deux** contrats enchaînés par l’Orchestrator.

---

## 3. Failure modes explicites

Catalogue **normatif** — chaque tool déclare le sous-ensemble qui lui applique.

| Code | Signification | `retryable` typique | Notes orchestrateur |
|------|---------------|---------------------|---------------------|
| `auth_missing` | Session / token / owner absent | non | Ne pas appeler le tool ; réponse 401 équivalent |
| `invalid_input` | Échec validation `input_schema` | non | Retourner au LLM avec détails champs |
| `tool_timeout` | Dépassement `timeout_ms` | par policy | Marquer audit ; pas de double exécution write |
| `external_service_down` | AFFiNE, SMTP, API tierce indisponible | oui si `read` | Message utilisateur clair |
| `permission_denied` | Rôle insuffisant (guest vs owner) | non | Pas de contournement LLM |
| `human_approval_required` | HITL non satisfait | non | État `pending_review` — pas d’exécution |
| `unsafe_action` | Garde-fou Safety Agent (contenu, scope) | non | Log audit obligatoire |
| `data_not_found` | Ressource absente (thread, fichier, ligne SQL) | non | Distinct de `invalid_input` |

**Failure modes mémoire (orchestration, pas tools) — référence croisée :**

`memory_unavailable`, `no_relevant_memory`, `context_too_large` — définis dans `COCO_AGENTIC_ORCHESTRATION.md` §2A ; ne pas dupliquer dans chaque memory tool sauf wrapper explicite.

**Mapping HTTP (indicatif, runtime futur) :**

| failure_mode | HTTP suggéré |
|--------------|--------------|
| `auth_missing` | 401 |
| `permission_denied` | 403 |
| `invalid_input` | 422 |
| `human_approval_required` | 409 |
| `tool_timeout` | 504 |
| `external_service_down` | 503 |
| `unsafe_action` | 403 |
| `data_not_found` | 404 |

---

## 4. HITL rules

### 4.1 Matrice par `side_effect_level`

| `side_effect_level` | Effet | `requires_human_approval` | Validation humaine |
|---------------------|-------|---------------------------|-------------------|
| `none` | Calcul, brouillon, suggestion | `false` par défaut | Non requise avant exécution |
| `read` | Lecture DB, mémoire, export preview | `false` par défaut | Non — mais `audit_log` si données sensibles |
| `write` | INSERT/UPDATE/DELETE, tâches persistées | **`true`** | **Obligatoire** |
| `external` | Email, API publique, AFFiNE, deploy | **`true`** | **Obligatoire** |

**Nuance read-only :** les tools `read` ne **nécessitent pas toujours** une validation humaine avant exécution. L’humain valide la **décision d’agir** via l’Orchestrator (intent), pas chaque lecture.

### 4.2 Familles à HITL obligatoire (même si mal classées)

Si un tool touche l’un de ces domaines, `requires_human_approval: true` **non négociable** :

- fournisseur (commande, annulation, litige, engagement contractuel)
- client (message sortant, remise, engagement commercial)
- email / SMS / messagerie sortante
- paiement / facturation / prélèvement
- GitHub (push, merge, PR merge)
- Railway / secrets / variables d’environnement / deploy
- suppression ou modification critique (mémoire owner, règles système, accès)

### 4.3 Whitelist write sans HITL

**Vide en v1.** Toute exception future doit être :

1. `side_effect_level: write` avec `requires_human_approval: false`
2. Justification produit + audit
3. `audit_log_required: true`
4. Effet réversible et borné (ex. brouillon interne non visible client)

### 4.4 Cycle HITL (rappel)

```text
proposed_action → pending_review → approved | rejected | modified_by_human → executed | failed
```

Si `human_approval_required` est retourné avant la file : l’Orchestrator crée `proposed_action` et **n’appelle pas** le handler d’exécution.

### 4.5 Séparation brouillon / envoi

| Étape | Tool type | HITL |
|-------|-----------|------|
| Rédaction | `draft_*`, `suggest_*` | non (`none`) |
| Envoi / publication | `send_*`, `publish_*` | **oui** (`external`) |

Exemple : `draft_customer_reply` (non) puis futur `send_customer_reply` (oui).

---

## 5. Exemples de tool contracts

Spécifications **documentaires** — `implemented: false`. Schémas simplifiés ; JSON Schema complet à produire lors de l’implémentation.

---

### 5.1 `create_affine_note`

| Champ | Valeur |
|-------|--------|
| `category` | `affine_workspace` |
| `side_effect_level` | `external` |
| `requires_human_approval` | `true` |
| `timeout_ms` | 30_000 |
| `retry_policy` | `{ "mode": "none", "max_attempts": 1 }` |
| `audit_log_required` | `true` |

**Description :** Propose la création d’une note Markdown dans l’espace AFFiNE de l’utilisateur (deep link / API future). N’impose pas de sync mémoire OpenChawn.

**input_schema (résumé) :**

```json
{
  "type": "object",
  "required": ["title", "body_md"],
  "properties": {
    "title": { "type": "string", "maxLength": 200 },
    "body_md": { "type": "string", "maxLength": 50_000 },
    "workspace_hint": { "type": "string", "description": "URL or affine:// hint" },
    "project_name": { "type": "string" }
  }
}
```

**output_schema (succès) :**

```json
{
  "type": "object",
  "required": ["note_ref", "deep_link"],
  "properties": {
    "note_ref": { "type": "string" },
    "deep_link": { "type": "string", "format": "uri" }
  }
}
```

**failure_modes :** `auth_missing`, `invalid_input`, `tool_timeout`, `external_service_down`, `permission_denied`, `human_approval_required`, `unsafe_action`

---

### 5.2 `import_restaurant_csv`

| Champ | Valeur |
|-------|--------|
| `category` | `data` |
| `side_effect_level` | `write` (apply) / `read` (dry_run) |
| `requires_human_approval` | `true` si `dry_run: false` |
| `timeout_ms` | 120_000 |
| `retry_policy` | `{ "mode": "none" }` |
| `audit_log_required` | `true` |

**Description :** Preview ou import CSV vers tables restaurant (**futures**). `dry_run: true` par défaut recommandé.

**input_schema (résumé) :**

```json
{
  "type": "object",
  "required": ["file_ref", "table_target"],
  "properties": {
    "file_ref": { "type": "string", "description": "Secure upload id" },
    "table_target": { "type": "string", "enum": ["sales", "suppliers", "inventory", "cash_register"] },
    "dry_run": { "type": "boolean", "default": true },
    "column_mapping": { "type": "object" }
  }
}
```

**output_schema :**

```json
{
  "type": "object",
  "required": ["rows_preview", "errors"],
  "properties": {
    "rows_preview": { "type": "array", "maxItems": 100 },
    "rows_accepted": { "type": "integer" },
    "errors": { "type": "array", "items": { "type": "object" } }
  }
}
```

**failure_modes :** `auth_missing`, `invalid_input`, `tool_timeout`, `permission_denied`, `human_approval_required`, `unsafe_action`, `data_not_found`

**NO GO :** Restaurant SQL runtime — contrat seulement.

---

### 5.3 `calculate_daily_cash`

| Champ | Valeur |
|-------|--------|
| `category` | `restaurant_analytics` |
| `side_effect_level` | `read` |
| `requires_human_approval` | `false` |
| `timeout_ms` | 15_000 |
| `retry_policy` | `{ "mode": "idempotent_only", "max_attempts": 2, "idempotency_key_required": true }` |
| `audit_log_required` | `false` |

**input_schema :**

```json
{
  "type": "object",
  "required": ["date"],
  "properties": {
    "date": { "type": "string", "format": "date" },
    "register_ids": { "type": "array", "items": { "type": "string" } },
    "project_name": { "type": "string" }
  }
}
```

**output_schema :**

```json
{
  "type": "object",
  "required": ["totals", "discrepancies"],
  "properties": {
    "totals": { "type": "object" },
    "discrepancies": { "type": "array" },
    "currency": { "type": "string", "default": "EUR" }
  }
}
```

**failure_modes :** `auth_missing`, `invalid_input`, `tool_timeout`, `data_not_found`, `permission_denied`

---

### 5.4 `suggest_supplier_alternative`

| Champ | Valeur |
|-------|--------|
| `category` | `supplier` |
| `side_effect_level` | `none` |
| `requires_human_approval` | `false` |
| `timeout_ms` | 20_000 |
| `retry_policy` | `{ "mode": "none" }` |
| `audit_log_required` | `false` |

**input_schema :**

```json
{
  "type": "object",
  "required": ["sku_or_product"],
  "properties": {
    "sku_or_product": { "type": "string" },
    "constraints": {
      "type": "object",
      "properties": {
        "max_price_delta_pct": { "type": "number" },
        "delivery_max_days": { "type": "integer" },
        "preferred_local": { "type": "boolean" }
      }
    }
  }
}
```

**output_schema :**

```json
{
  "type": "object",
  "required": ["ranked_suppliers"],
  "properties": {
    "ranked_suppliers": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["supplier_id", "score", "rationale"],
        "properties": {
          "supplier_id": { "type": "string" },
          "score": { "type": "number" },
          "rationale": { "type": "string" }
        }
      }
    }
  }
}
```

**failure_modes :** `invalid_input`, `data_not_found`, `tool_timeout`

---

### 5.5 `draft_customer_reply`

| Champ | Valeur |
|-------|--------|
| `category` | `communication` |
| `side_effect_level` | `none` |
| `requires_human_approval` | `false` |
| `timeout_ms` | 25_000 |
| `audit_log_required` | `false` |

**Description :** Produit un brouillon uniquement. L’envoi exige un tool séparé (`send_*`) en `external` + HITL.

**input_schema :**

```json
{
  "type": "object",
  "required": ["thread_id", "tone"],
  "properties": {
    "thread_id": { "type": "string" },
    "tone": { "type": "string", "enum": ["professional", "friendly", "firm", "apologetic"] },
    "constraints": { "type": "string" },
    "language": { "type": "string", "description": "BCP-47; runtime language policy applies" }
  }
}
```

**output_schema :**

```json
{
  "type": "object",
  "required": ["draft_text"],
  "properties": {
    "draft_text": { "type": "string" },
    "warnings": { "type": "array", "items": { "type": "string" } }
  }
}
```

**failure_modes :** `auth_missing`, `invalid_input`, `data_not_found`, `unsafe_action`, `tool_timeout`

---

### 5.6 `create_followup_task`

| Champ | Valeur |
|-------|--------|
| `category` | `data` |
| `side_effect_level` | `write` |
| `requires_human_approval` | `true` |
| `timeout_ms` | 10_000 |
| `audit_log_required` | `true` |

**input_schema :**

```json
{
  "type": "object",
  "required": ["title", "due_at"],
  "properties": {
    "title": { "type": "string", "maxLength": 300 },
    "due_at": { "type": "string", "format": "date-time" },
    "assignee": { "type": "string" },
    "context": { "type": "string" },
    "project_name": { "type": "string" },
    "linked_memory_ids": { "type": "array", "items": { "type": "string" } }
  }
}
```

**output_schema :**

```json
{
  "type": "object",
  "required": ["task_id"],
  "properties": {
    "task_id": { "type": "string" },
    "status": { "type": "string", "enum": ["pending", "open"] }
  }
}
```

**failure_modes :** `auth_missing`, `invalid_input`, `permission_denied`, `human_approval_required`, `tool_timeout`, `unsafe_action`

---

### 5.7 `check_provider_health`

| Champ | Valeur |
|-------|--------|
| `category` | `admin_devops` |
| `side_effect_level` | `read` |
| `requires_human_approval` | `false` |
| `timeout_ms` | 8_000 |
| `retry_policy` | `{ "mode": "with_backoff", "max_attempts": 3, "backoff_ms": 500 }` |
| `audit_log_required` | `true` |

**Description :** Diagnostic lecture seule des providers LLM (latence, dispo). **Ne modifie pas** routing ni `ProviderManager`. Aligné observability / staging.

**input_schema :**

```json
{
  "type": "object",
  "properties": {
    "provider_ids": { "type": "array", "items": { "type": "string" } },
    "include_latency_probe": { "type": "boolean", "default": false }
  }
}
```

**output_schema :**

```json
{
  "type": "object",
  "required": ["providers"],
  "properties": {
    "providers": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "status"],
        "properties": {
          "id": { "type": "string" },
          "status": { "type": "string", "enum": ["up", "degraded", "down", "unknown"] },
          "latency_ms": { "type": "integer" },
          "last_error": { "type": "string" }
        }
      }
    }
  }
}
```

**failure_modes :** `auth_missing`, `permission_denied`, `tool_timeout`, `external_service_down`

**NO GO :** implémentation qui touche `app/llm/*` ou Phase 2 — ce contrat décrit l’**interface** de diagnostic future.

---

## 6. MCP compatibility

### 6.1 Décision actuelle

**Pas d’intégration MCP runtime.** Les Tool Contracts internes OpenChawn sont la source de vérité.

### 6.2 Stratégie d’adaptation future

```text
OpenChawn ToolContract (registry)
        │
        ├─► MCP Tool Descriptor (name, inputSchema, outputSchema)
        │         side_effect_level → MCP annotations (readOnlyHint, destructiveHint)
        │         requires_human_approval → orchestrator gate (pas MCP natif)
        │
        └─► MCP Resource / Prompt (optionnel) pour contexte statique
```

| Champ interne | Mapping MCP (indicatif) |
|---------------|-------------------------|
| `name` | `tool.name` |
| `description` | `tool.description` |
| `input_schema` | `inputSchema` |
| `output_schema` | documentation + validation côté serveur |
| `failure_modes` | erreurs structurées dans `isError` + contenu JSON |
| `timeout_ms` | timeout transport MCP |
| HITL | **reste côté OpenChawn Orchestrator** — MCP n’exécute pas sans passe HITL |

**Ordre d’introduction MCP :**

1. Contrats internes stables (ce document) + HITL en staging  
2. Pilote **un** tool `read` / `none` (ex. `check_provider_health`)  
3. Tools `external` uniquement après audit Safety Agent  

### 6.3 Ce que MCP ne remplace pas

- Validation `side_effect_level` / HITL  
- `audit_log_required`  
- Guest vs owner permissions  
- Politique langue et mémoire OpenChawn  

---

## 7. Runtime target

Flow normatif lorsque l’Orchestrator et le registre seront implémentés (spec seule aujourd’hui).

```text
┌──────────────────┐
│   User intent    │  message UI, objectif, projet
└────────┬─────────┘
         ▼
┌──────────────────┐
│   Orchestrator   │  auth, quota, policy, audit_id
└────────┬─────────┘
         │ resolve intent → tool candidate(s)
         ▼
┌──────────────────┐
│ ToolContract     │  validate input_schema (dry)
│   selection      │  pick version, category, agent owner
└────────┬─────────┘
         │
         ├─ requires_human_approval?
         │       yes ▼
         │   ┌─────────────┐
         │   │ HITL queue  │  proposed_action → pending_review
         │   └──────┬──────┘
         │          │ approved | modified_by_human
         │          no ────────┐
         ▼                      ▼
┌──────────────────┐
│ Tool execution   │  timeout, retry_policy, side_effect guard
│  (Tool Agent)    │
└────────┬─────────┘
         │
         ├─ ok ──► Result (output_schema)
         └─ fail ► failure_mode envelope
         ▼
┌──────────────────────────────────────────┐
│ Post-processing                          │
│  • Memory writeback (if policy allows)   │
│  • AFFiNE link / note ref (if tool)      │
│  • audit log (if audit_log_required)     │
└────────┬─────────────────────────────────┘
         ▼
┌──────────────────┐
│ User response    │  text + structured artifacts + HITL status
└──────────────────┘
```

**Chemin actuel (sans registre) :** `POST /chat` → LLM direct — voir `COCO_AGENTIC_ORCHESTRATION.md` §3. Ce flow **remplace progressivement** l’exécution implicite d’actions par des tools enregistrés.

---

## 8. NO GO actuels

| Interdit | Détail |
|----------|--------|
| **Code runtime** | Pas de module `app/tools/`, pas de registry YAML chargé en prod |
| **MCP runtime** | Pas de serveur MCP, pas de clients connectés |
| **AFFiNE sync** | `create_affine_note` = spec ; pas de sync bidirectionnelle mémoire |
| **Restaurant SQL** | `import_restaurant_csv` / analytics SQL = spec uniquement |
| **LUTHOR** | Hors registre OpenChawn |
| **Phase 2 ProviderManager** | `check_provider_health` ne autorise pas de refactor `app/llm/*` |
| **main / prod** | Doc et staging sandbox seulement |
| **Railway** | Aucun tool `deploy_*` actif |
| **Patch langue UI** | `draft_customer_reply.language` suit policy runtime — pas de changement UI |
| **`static/index.html`** | Pas de UI HITL dans ce livrable |
| **Interface paths skeleton** | Option B séparée — après GO code explicite |

---

## Registry index (v1 documentaire)

| `name` | `category` | `side_effect_level` | HITL | `implemented` |
|--------|------------|---------------------|------|---------------|
| `create_affine_note` | `affine_workspace` | `external` | oui | false |
| `import_restaurant_csv` | `data` | `write` | oui (apply) | false |
| `calculate_daily_cash` | `restaurant_analytics` | `read` | non | false |
| `suggest_supplier_alternative` | `supplier` | `none` | non | false |
| `draft_customer_reply` | `communication` | `none` | non | false |
| `create_followup_task` | `data` | `write` | oui | false |
| `check_provider_health` | `admin_devops` | `read` | non | false |

---

## Références

| Document | Lien |
|----------|------|
| Orchestration & compartiments | `docs/COCO_AGENTIC_ORCHESTRATION.md` |
| AFFiNE second brain | `docs/COCO_AFFINE_SECOND_BRAIN.md` |
| Évolution contrôlée | `docs/CONTROLLED_EVOLUTION_DOCTRINE.md` |
| API staging | `docs/API_STABILIZATION_V11_7.md` |

---

*Document créé en mode DOC ONLY — Tool Contract Registry spec v1. Aucun changement runtime.*
