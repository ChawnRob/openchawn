# COCO Agentic Architecture — Orchestration & Compartmentalization

**Repo:** OpenChawn (COCO)  
**Branch cible doc:** `sandbox/staging-v11-7`  
**Statut:** documentation d’architecture uniquement — aucune implémentation runtime  
**Dernière révision doc:** 2026-06-03

---

## 1. Objectif général

COCO n’est pas un simple chatbot. COCO est l’**orchestrateur agentique** d’OpenChawn : un gouverneur opérationnel qui coordonne mémoire, outils, actions, validation humaine, analyse de données et (à terme) l’espace de travail AFFiNE.

| Rôle | Description |
|------|-------------|
| **Mémoire** | Récupérer, filtrer, compresser et injecter un **Context Pack** — jamais la mémoire brute entière |
| **Outils** | Exécuter des **Tool Contracts** explicites (schémas, échecs, timeouts, effets de bord) |
| **Actions** | Proposer et exécuter des effets monde (notes, SQL, relances, tâches) via routage contrôlé |
| **Validation humaine (HITL)** | Interrompre, faire réviser et approuver avant tout effet externe ou critique |
| **Data analysis** | Transformer données restaurant brutes → tableaux → alertes → actions recommandées |
| **Workspace futur** | Lier décisions et traces à AFFiNE (second brain) sans prétendre stocker les docs utilisateur |

**Principe directeur :** le LLM **décide et rédige** ; le runtime **valide, route, persiste et exécute** — jamais l’inverse pour les effets critiques.

---

## 2. Les 5 compartiments principaux

Chaque compartiment est une **frontière conceptuelle** : interfaces stables, responsabilités séparées, évolution indépendante. Aucun compartiment ne remplace les garde-fous globaux (HITL, NO GO, sandbox).

### A. Memory Compression / Context Engineering

**Mission :** fournir au modèle uniquement ce qui est **pertinent, borné et auditable** pour la requête courante.

| Étape | Rôle |
|-------|------|
| Récupération mémoire | Policy-driven retrieval (projet, profil, cognitive state) — pas de dump global |
| Filtrage | Exclusion secrets, contradictions non résolues, bruit, entrées archivées selon policy |
| Compression | Regroupement / résumés structurés (`compressed`, stable_facts, key_decisions) |
| **Context Pack** | Artefact unique injecté dans le prompt : taille max, sections typées, provenance tracée |
| Anti-pattern | **Ne jamais** injecter toute la mémoire utilisateur « au cas où » |

**Failure modes (contrat retrieval → orchestrateur) :**

| Code | Signification | Comportement attendu |
|------|---------------|----------------------|
| `memory_unavailable` | Store inaccessible ou erreur I/O | Chat dégradé sans mémoire ; log + métrique ; pas de writeback silencieux |
| `no_relevant_memory` | Aucun candidat au-dessus du seuil | Context Pack vide explicite ; le modèle ne doit pas inventer des souvenirs |
| `context_too_large` | Pack dépasse budget tokens/caractères | Troncature ordonnée (priorité : règles > requête > récent > compressé > archive) |

**Lien runtime actuel :** `build_layered_memory_context` / retrieval policy (voir `docs/memory_compression_layer.md`, `docs/retrieval_policy_layer.md`). **Cible :** Memory Agent + Context Pack builder sous Orchestrator.

---

### B. Tool Calling

**Principe :** *Every tool is a contract.*

Aucun « tool » implicite dans le prompt. Chaque capacité actionnable est un **Tool Contract** versionné.

**Champs obligatoires du contrat :**

| Champ | Description |
|-------|-------------|
| `name` | Identifiant stable (snake_case) |
| `input_schema` | JSON Schema (ou équivalent) — champs requis, types, bornes |
| `output_schema` | Forme de succès ; champs d’erreur structurés |
| `failure_modes` | Liste explicite (`timeout`, `permission_denied`, `validation_error`, …) |
| `timeout_ms` | Plafond d’exécution |
| `retry_policy` | `none` \| `idempotent_only` \| `with_backoff` + max attempts |
| `side_effect_level` | `none` \| `read` \| `write` \| `external` |
| `requires_human_approval` | `true` \| `false` |

**Règle d’or :** `side_effect_level` ∈ {`write`, `external`} ⇒ `requires_human_approval: true` sauf exception documentée et auditée.

**Exemples de contrats (spécification seule — non implémentés ici) :**

| Tool | Input (résumé) | Output (résumé) | side_effect | HITL |
|------|----------------|-----------------|-------------|------|
| `create_affine_note` | `title`, `body_md`, `workspace_hint?` | `note_id`, `deep_link` | `external` | oui |
| `import_restaurant_csv` | `file_ref`, `table_target`, `dry_run` | `rows_preview`, `errors[]` | `write` | oui |
| `calculate_daily_cash` | `date`, `register_ids[]` | `totals`, `discrepancies[]` | `read` | non |
| `suggest_supplier_alternative` | `sku`, `constraints` | `ranked_suppliers[]`, `rationale` | `none` | non |
| `draft_customer_reply` | `thread_id`, `tone` | `draft_text` | `none` | non (envoi = autre tool) |
| `create_followup_task` | `due_at`, `assignee`, `context` | `task_id` | `write` | oui si assignation externe |

**Lien cible :** Tool Agent exécute ; Orchestrator valide le contrat ; HITL gate si requis.

---

### C. Human-in-the-Loop (HITL)

**Définition :** couche d’**interruption** — pas un simple flag UI. L’agent **pause**, l’humain **révise**, **approuve ou modifie**, l’agent **continue** ou **abort**.

```text
agent proposes → PAUSE → human reviews → approve | reject | modify → agent continues | stops
```

**États du cycle d’action :**

```text
proposed_action
    → pending_review
        → approved → executed → (failed | done)
        → rejected → (archived | logged)
        → modified_by_human → approved → executed → …
```

| État | Description |
|------|-------------|
| `proposed_action` | Tool Contract rempli, en attente de file HITL |
| `pending_review` | Visible dans UI / notification ; agent bloqué sur cette action |
| `approved` | Humain a validé tel quel |
| `rejected` | Humain refuse ; raison obligatoire |
| `modified_by_human` | Paramètres ou contenu édités avant exécution |
| `executed` | Effet appliqué ; trace persistée |
| `failed` | Exécution erreur post-approbation ; pas de retry auto sur effets externes |

**HITL obligatoire pour :**

- envoi email / message client ou fournisseur
- modification SQL (INSERT/UPDATE/DELETE) sur données restaurant
- publication externe (réseaux, avis, listings)
- action fournisseur / client engageante (commande, annulation, litige)
- paiement / facturation / prélèvement
- changement GitHub / Railway / secrets / déploiement
- suppression ou modification critique (mémoire owner, règles système, accès)

**Lien cible :** HITL Safety Agent + file d’attente UI ; aligné sur `docs/CONTROLLED_EVOLUTION_DOCTRINE.md` (rien de irréversible sans humain).

---

### D. Multi-Agent Orchestration

**Définition :** coordination d’**agents spécialisés** (rôles, prompts, policies) sous un **Orchestrator** unique. Pas d’implémentation multi-agent en runtime aujourd’hui — ce document fixe le découpage.

**Agents futurs (spécialisation) :**

| Agent | Responsabilité |
|-------|----------------|
| Memory Agent | Retrieval, Context Pack, compression hints |
| Tool Agent | Validation contrat, dispatch, retry, idempotence |
| Data Analysis Agent | Nettoyage, agrégations, anomalies sur données brutes |
| Restaurant Finance Agent | Caisse, TVA, charges, fin de mois |
| Supplier Agent | Alternatives, délais, ruptures |
| Promotion Agent | Campagnes, marge, calendrier |
| Review/Reputation Agent | Avis, réponses, escalade |
| HITL Safety Agent | Classification risque, file d’approbation, audit |
| AFFiNE Workspace Agent | Notes, liens, structure second brain (sans sync complète imposée) |

**Règle non négociable :**

> Aucun agent ne peut exécuter une **action critique** directement.  
> Tout passe par **Tool Contract** + **HITL** si effet `write` ou `external`.

```text
                    ┌─────────────────┐
                    │  Orchestrator   │
                    └────────┬────────┘
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   Memory Agent         Tool Agent          Domain Agents
         │                   │              (Finance, Supplier, …)
         └─────────┬─────────┴─────────┬─────────┘
                   ▼                   ▼
            Context Pack          Tool Contract
                   │                   │
                   └─────────┬─────────┘
                             ▼
                      HITL (if required)
                             ▼
                      Execution layer
```

---

### E. MCP (Model Context Protocol)

**Vision :** MCP comme **standard futur** pour connecter outils, bases, services, fichiers et APIs externes de façon interchangeable.

**Décision actuelle (2026-06-03) :** **pas d’intégration MCP runtime.**

| Raison | Détail |
|--------|--------|
| Contrats internes d’abord | Tool Contracts OpenChawn doivent être propres, testés, versionnés |
| Surface d’attaque | MCP multiplie les connecteurs avant HITL mature |
| Staging focus | Stabiliser chat + mémoire + quota avant nouveaux protocoles |

**Ordre recommandé :** Tool Contract Registry (spec + registry local) → HITL sur `write`/`external` → puis pilote MCP pour un connecteur lecture seule.

---

## 3. Runtime path actuel

Chemin réel aujourd’hui (staging V11.7, handler stabilisé) — **sans Orchestrator dédié** :

```text
┌─────────────┐
│   COCO UI   │  static/index.html — chat, profils, mémoire UI
└──────┬──────┘
       │ POST /chat  ou  POST /api/chat
       ▼
┌─────────────────────┐
│   chat handler      │  app/api/chat.py — handle_chat_request
│   (auth / quota)    │  guest quota, owner vs guest
└──────┬──────────────┘
       │ assemble_chat_generation_inputs
       ▼
┌─────────────────────┐
│  memory context     │  build_layered_memory_context (fractal_memory)
│  + language policy  │  profiles, second brain snippet, rules
└──────┬──────────────┘
       │ generate_response
       ▼
┌─────────────────────┐
│  llm gateway        │  app/llm/gateway.py
│  provider adapters  │  app/llm/adapters/* (HTTP, etc.)
└──────┬──────────────┘
       │ output text
       ▼
┌─────────────────────┐
│  response JSON      │  output, memory_used, lang, route_signature
└──────┬──────────────┘
       │ write_exchange (si succès HTTP 200)
       ▼
┌─────────────────────┐
│  memory persist     │  fractal_memory — chat_user / chat_guest
│  (+ consolidation   │  hint optionnel, non bloquant)
│   recommendation)   │
└─────────────────────┘
```

**Ce qui manque vs cible agentique :** Decision Router, Tool Contract dispatch, HITL gate, agents domaine, exécution SQL/AFFiNE post-approbation.

---

## 4. Runtime cible agentique

Architecture **cible** — à atteindre par phases ; ne pas confondre avec le déploiement actuel.

```text
┌─────────────┐
│   COCO UI   │  chat + inbox HITL + tableaux restaurant (futur)
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│    Orchestrator     │  intent, budget, policy, audit id
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│    Context Pack     │  Memory Agent — borné, tracé
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│   Decision Router   │  répondre | appeler tool | déléguer agent | escalader HITL
└──────┬──────────────┘
       │
       ├──────────────────┬────────────────────┐
       ▼                  ▼                    ▼
┌──────────────┐  ┌──────────────┐    ┌──────────────┐
│ Tool Contract│  │ Domain Agent │    │  LLM (chat)  │
│   dispatch   │  │  (finance,   │    │  rédaction   │
│              │  │   supplier…) │    │              │
└──────┬───────┘  └──────┬───────┘    └──────┬───────┘
       │                 │                    │
       └────────┬────────┴────────────────────┘
                ▼
       ┌─────────────────┐
       │  HITL if needed │  pending_review → approved | rejected | modified
       └────────┬────────┘
                ▼
       ┌─────────────────────────────────────────┐
       │  Action / Memory / AFFiNE / SQL (future) │
       └────────┬────────────────────────────────┘
                ▼
       ┌─────────────────┐
       │    response     │  texte + traces + liens tâches / notes
       └─────────────────┘
```

---

## 5. Restaurant Data Governor

**Direction produit :** COCO transforme les **données brutes** du restaurant en **tableaux lisibles**, puis en **décisions** et **actions** — toujours avec HITL sur les effets externes.

```text
raw data (CSV, caisse, exports, emails structurés)
    → data analysis (nettoyage, typage, anomalies)
    → clean SQL tables (schéma restaurant — futur)
    → analytics (KPIs, tendances, seuils)
    → alerts (TVA, fin de mois, rupture, marge)
    → recommended actions (tools proposés, pas exécutés seuls)
    → HITL approval
    → execution | reminder | AFFiNE note
```

**Exemples de flux métier (spécification) :**

| Domaine | Entrée brute | Sortie analytique | Action typique (post-HITL) |
|---------|--------------|-------------------|----------------------------|
| Caisse journalière | tickets / Z | écart, total jour | `create_followup_task` si écart |
| TVA à provisionner | ventes période | montant à provisionner | alerte + note AFFiNE |
| Charges estimées | factures, récurrence | prévision fin de mois | tableau + rappel |
| Fournisseurs alternatifs | catalogue, historique | `suggest_supplier_alternative` | brouillon commande (HITL) |
| Promotions | marge, stock | scénarios | brouillon campagne (HITL) |
| Relances urgentes | impayés, délais | liste priorisée | `draft_customer_reply` + envoi (HITL) |
| Alertes fin de mois | agrégats | dashboard + checklist | tâches + notes |

**Agents concernés :** Data Analysis Agent, Restaurant Finance Agent, Supplier / Promotion / Review agents — tous sous règle Tool Contract + HITL.

---

## 6. Boundaries / NO GO actuels

Explicitement **hors scope** tant qu’un GO produit + humain ne dit pas le contraire :

| NO GO | Raison |
|-------|--------|
| **LUTHOR** | Projet / intégration séparée — ne pas mélanger avec OpenChawn staging |
| **Phase 2 ProviderManager** | Refactor providers non lancé ; ne pas toucher `app/llm/*` ni gateway behavior |
| **MCP runtime** | Contrats internes et HITL d’abord (section E) |
| **AFFiNE sync complet** | Second brain = ouverture workspace utilisateur ; pas de sync mémoire↔AFFiNE imposée |
| **Restaurant SQL implementation** | Schéma et ETL non déployés — doc et contrats seulement |
| **main / prod** | Travail sur `sandbox/staging-v11-7` ; pas de merge prod sans checklist |
| **Patch langue UI** | Policy runtime stabilisée V11.6+ — pas de retouche UI/langue sans ticket dédié |
| **Refactor `app/llm`** | Adapters extraits (#3) — gel jusqu’à Phase 2 explicitement approuvée |
| **Changement Railway** | Config deploy inchangée pour cette initiative doc |
| **`static/index.html`** | Pas de modification UI dans le cadre de ce document |
| **`settings.py` / ProviderManager** | Non touchés |
| **Implémentation Tool / HITL / Orchestrator** | Ce fichier est **architecture seule** — pas Phase 2 code |

---

## 7. Next recommended move

Trois options possibles après cette doc — avec **GO / NO GO** et **une** recommandation unique.

### Option A — Observability quota diagnostics

| | |
|---|---|
| **Contenu** | Métriques et traces autour du 429 guest, corrélation session/IP, dashboards staging |
| **GO** | ✅ Oui — faible risque, aligné commit récent `c0535fc`, pas de refactor LLM |
| **NO GO** | ❌ Si ça dérive vers changement Railway ou prod |

### Option B — Interface paths skeleton

| | |
|---|---|
| **Contenu** | Routes/types vides pour Orchestrator, HITL queue, Tool Registry (stubs sans logique) |
| **GO** | ⚠️ Conditionnel — utile mais risque de toucher `app/` trop tôt |
| **NO GO** | ❌ Maintenant — sans spec Tool Contract, les stubs deviennent dette |

### Option C — Tool Contract Registry spec

| | |
|---|---|
| **Contenu** | `docs/COCO_TOOL_CONTRACT_REGISTRY.md` — schéma, exemples, versioning, lien HITL |
| **GO** | ✅ **Recommandé** — doc-only, débloque B et MCP plus tard, zéro runtime |
| **NO GO** | ❌ Si on y mélange implémentation Python dans le même PR |

---

### Recommandation unique

**Prochaine action : Option C — Tool Contract Registry spec (doc only).**

Enchaînement logique :

1. ✅ Ce document (`COCO_AGENTIC_ORCHESTRATION.md`) — compartiments + chemins runtime  
2. → **Option C** — registry spec des tools (toujours sans code)  
3. → Option A — observability quota (petit code isolé, après GO)  
4. → Option B — skeleton code (après registry + GO Phase 2)

---

## Références internes

| Document | Lien |
|----------|------|
| Mémoire / compression | `docs/memory_compression_layer.md` |
| Retrieval policy | `docs/retrieval_policy_layer.md` |
| Carte mémoire V11.7 | `docs/OPENCHAWN_MEMORY_MAP_V11_7.md` |
| Évolution contrôlée | `docs/CONTROLLED_EVOLUTION_DOCTRINE.md` |
| AFFiNE second brain | `docs/COCO_AFFINE_SECOND_BRAIN.md` |
| API staging | `docs/API_STABILIZATION_V11_7.md` |

---

*Document créé en mode DOC ONLY — aucun changement runtime associé.*
