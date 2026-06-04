# COCO Input Understanding Guard — Specification

**Repo:** OpenChawn (COCO)
**Branch cible doc:** `sandbox/staging-v11-7`
**Statut:** specification + comportement attendu — **Phase 0 doc only, aucune implémentation runtime**
**Parents:** `docs/COCO_AGENTIC_ORCHESTRATION.md`, `docs/COCO_TOOL_CONTRACT_REGISTRY.md`
**Dernière révision doc:** 2026-06-04

---

## 1. But de l'Intent Guard

La langue est stabilisée (V11.6+). Le défaut résiduel n'est plus *quelle langue* mais *quelle intention*. COCO peut encore :

- confondre une **question** avec une **revendication** ;
- **extrapoler** une action non demandée ;
- mélanger les **contextes** (exemple utilisateur pris pour instruction runtime).

> **Cas canonique du bug**
> User : « Well said, who made you? »
> Mauvais : « So if you're claiming to be my creator… »
> Bon : réponse factuelle sur l'origine de COCO, **sans** supposer que l'utilisateur revendique être le créateur.

L'**Input Understanding Guard** (alias *COCO Intent Guard* / *Intent Router*) est une couche **avant génération** qui produit un petit objet d'intention. Elle ne génère pas la réponse ; elle **borne** la génération : intention principale, mode de réponse, inférences interdites, besoins (tool / HITL / clarification).

**Principe :** comprendre avant de répondre. Une mauvaise lecture de l'intention est plus coûteuse qu'une réponse plus lente.

---

## 2. Contrat `InputUnderstandingResult`

Objet produit pour **chaque** message utilisateur, avant le Context Pack et l'Orchestrator.

| Champ | Type | Description |
|-------|------|-------------|
| `raw_message` | `string` | Message utilisateur brut, **jamais réécrit ni sanitizé** ici |
| `detected_language` | `string` | Code langue de surface (réutilise `derive_response_language_trace`, **lecture seule**) |
| `primary_intent` | `enum` | Intention dominante (§3) |
| `secondary_intents` | `enum[]` | Intentions additionnelles (ex. `go_no_go_decision` + `architecture_scope_check`) |
| `response_mode` | `enum` | Style de réponse attendu (§2.1) |
| `requires_tool` | `boolean` | Une capacité actionnable serait nécessaire (Tool Contract) |
| `requires_human_review` | `boolean` | HITL obligatoire avant tout effet (§3.10) |
| `requires_clarification` | `boolean` | Ambiguïté : demander avant d'agir/répondre largement |
| `project_scope` | `string \| null` | Projet/contexte ciblé (ex. `openchawn`, `staging`, `null` si général) |
| `forbidden_inferences` | `string[]` | Suppositions explicitement interdites pour ce message (§4) |
| `context_needed` | `string[]` | Éléments à charger (ex. `git_status`, `recent_commits`, `runtime_logs`) |
| `confidence` | `number` | 0.0–1.0 ; sous seuil ⇒ `requires_clarification: true` |
| `safe_instruction_for_response` | `string` | Consigne brève et bornée transmise au générateur (pas de CoT, pas d'action) |

### 2.1 `response_mode` (valeurs)

| Valeur | Usage |
|--------|-------|
| `factual_short_answer` | Réponse factuelle courte (identité, faits simples) |
| `project_status_report` | État projet : commits, risques, next move |
| `cold_diagnosis` | Debug : preuves d'abord, pas d'action |
| `bounded_instruction` | Produire une instruction claire + scope + NO GO |
| `go_no_go_review` | Vérifier status/scope/tests/branch/prod avant verdict |
| `deescalate` | Désamorcer, revenir aux preuves |
| `strategy_with_reframe` | Stratégie produit + recadrage hiérarchie projet |
| `architecture_explainer` | Expliquer la couche + chemin progressif |
| `language_passthrough` | Respecter `response_language_mode`, ne pas interférer |
| `hitl_checklist` | Action à effet : checklist + confirmation, jamais d'exécution directe |
| `clarify_first` | Poser une question de clarification avant de répondre largement |

---

## 3. Intentions minimales

Chaque intention = un `primary_intent` reconnaissable + une règle de comportement.

### 3.1 `identity_origin_question`
**Exemples :** who made you? · who created you? · qui t'a créé ? · qui t'a conçu ?
**Règle :** répondre **factuellement** sur l'origine. **Ne pas** supposer que l'utilisateur revendique être le créateur.
**response_mode :** `factual_short_answer`

### 3.2 `project_status_question`
**Exemples :** où on en est ? · what is the current state? · résume le checkpoint
**Règle :** état projet — commits, risques, next move.
**response_mode :** `project_status_report` · **context_needed :** `git_status`, `recent_commits`

### 3.3 `technical_debug_request`
**Exemples :** analyse ce retour shell · pourquoi ça crash ? · curl retourne 429
**Règle :** diagnostiquer froidement, **preuves d'abord**, aucune action dangereuse (pas de rollback/push spontané).
**response_mode :** `cold_diagnosis` · **context_needed :** `runtime_logs`, `runtime_commit`, `environment`

### 3.4 `action_instruction`
**Exemples :** fais le prompt · donne le next move · envoie à Cursor
**Règle :** produire une instruction claire, **bornée**, avec NO GO si nécessaire.
**response_mode :** `bounded_instruction`

### 3.5 `go_no_go_decision`
**Exemples :** GO ? · on merge ? · on push ?
**Règle :** vérifier status, scope, tests, branch, **prod safety** avant verdict.
**response_mode :** `go_no_go_review` · **context_needed :** `git_status`, `branch`, `tests_state`

### 3.6 `emotional_frustration`
**Exemples :** ça me saoule · tu as tout niqué · putain ça marche pas
**Règle :** **désamorcer**, revenir aux preuves, ne pas amplifier. Une frustration **n'autorise pas** un rollback ou un push.
**response_mode :** `deescalate`

### 3.7 `product_strategy_question`
**Exemples :** quel secteur pour COCO ? · SaaS ou GaaS ? · quel but final ?
**Règle :** répondre stratégie produit, mais **recadrer** avec la hiérarchie projet.
**response_mode :** `strategy_with_reframe`

### 3.8 `tool_or_architecture_question`
**Exemples :** quel outil pour ne pas confondre ? · MCP ? · Tool Calling ?
**Règle :** expliquer la couche architecture et proposer un **chemin progressif**.
**response_mode :** `architecture_explainer`

### 3.9 `language_or_translation_request`
**Exemples :** répond en anglais · traduit en espagnol · pourquoi il mélange les langues ?
**Règle :** respecter `response_language_mode`. **Ne pas mélanger** avec l'Intent Guard — la langue reste pilotée par `app/core/language_policy.py`.
**response_mode :** `language_passthrough`

### 3.10 `unsafe_or_side_effect_action`
**Exemples :** merge main · modifie Railway · envoie un message client · supprime un service
**Règle :** **HITL obligatoire**. Demander confirmation ou produire une checklist. **Ne jamais exécuter directement.**
**response_mode :** `hitl_checklist` · **requires_human_review :** `true`

---

## 4. Forbidden inference rules

La couche **empêche** COCO de supposer :

| # | Inférence interdite | Déclencheur typique |
|---|---------------------|---------------------|
| FI-1 | que l'utilisateur **revendique** quelque chose s'il **pose une question** | « who made you? » |
| FI-2 | que l'utilisateur veut lancer une **action dangereuse** sans **GO explicite** | « on push ? » |
| FI-3 | que **LUTHOR** doit être intégré quand il est seulement **mentionné** | « et LUTHOR ? » |
| FI-4 | qu'une **question stratégique** implique un **changement de code** | « SaaS ou GaaS ? » |
| FI-5 | qu'une **erreur émotionnelle** autorise un **rollback ou push** | « ça me saoule » |
| FI-6 | qu'une **question en anglais** impose un **changement global de langue** | « who made you? » (FR session) |
| FI-7 | qu'un **exemple utilisateur** est une **instruction runtime** | « par exemple merge main » |

**Convention de nommage** (valeurs de `forbidden_inferences`) :
`do_not_assume_user_claims_creator`, `do_not_launch_action_without_go`, `do_not_integrate_luthor_on_mention`, `do_not_change_code_on_strategy_question`, `do_not_act_on_emotion`, `do_not_switch_global_language_on_one_message`, `do_not_treat_example_as_runtime_instruction`.

---

## 5. Exemples bons / mauvais

### Exemple 1 — identité
```text
User: "Well said, who made you?"

InputUnderstandingResult:
  primary_intent: identity_origin_question
  response_mode: factual_short_answer
  forbidden_inferences: [do_not_assume_user_claims_creator]
  requires_tool: false
  requires_human_review: false
  requires_clarification: false

Bon  : "COCO was created as part of the OpenChawn project. COCO is the
        interface, and OpenChawn is the orchestration layer behind it."
Mauvais : "So if you're claiming to be my creator..."   ← FI-1
```

### Exemple 2 — LUTHOR
```text
User: "On branche LUTHOR ?"

InputUnderstandingResult:
  primary_intent: go_no_go_decision
  secondary_intents: [architecture_scope_check]
  response_mode: go_no_go_review
  forbidden_inferences: [do_not_integrate_luthor_on_mention, do_not_launch_action_without_go]
  requires_human_review: true

Bon : NO GO tant que COCO stable, orchestrator stable, mémoire fiable,
      providers propres ne sont pas tous vérifiés. Donner la checklist.
Mauvais : commencer à câbler LUTHOR.   ← FI-3
```

### Exemple 3 — crash Railway
```text
User: "Ça a crashé sur Railway."

InputUnderstandingResult:
  primary_intent: technical_debug_request
  response_mode: cold_diagnosis
  context_needed: [runtime_logs, runtime_commit, environment]
  forbidden_inferences: [do_not_act_on_emotion]
  requires_human_review: false

Bon : demander / inspecter runtime, logs, commit, environnement.
Mauvais : rollback ou redeploy au hasard.   ← FI-5
```

### Exemple 4 — prompt Cursor
```text
User: "Fais-moi un prompt Cursor."

InputUnderstandingResult:
  primary_intent: action_instruction
  response_mode: bounded_instruction
  requires_tool: false

Bon : produire un prompt borné — scope, fichiers autorisés, NO GO, validation.
Mauvais : prompt vague sans périmètre ni garde-fous.
```

---

## 6. Placement dans l'architecture

L'Intent Guard se place **avant** le Context Pack : il oriente *quoi* récupérer et *comment* répondre.

```text
┌─────────────┐
│ User Input  │  message brut
└──────┬──────┘
       ▼
┌─────────────────────────┐
│ Input Understanding     │  InputUnderstandingResult
│ Guard (Intent Router)   │  intent · response_mode · forbidden_inferences
└──────┬──────────────────┘
       ▼
┌─────────────────────────┐
│ Context Pack            │  borné par context_needed / project_scope
└──────┬──────────────────┘
       ▼
┌─────────────────────────┐
│ Orchestrator            │  applique response_mode + garde-fous
└──────┬──────────────────┘
       ├───────────────┬────────────────┐
       ▼               ▼                ▼
┌────────────┐  ┌────────────┐   ┌────────────┐
│ LLM (chat) │  │ Tool        │   │ HITL gate  │
│ rédaction  │  │ Contract    │   │ if needed  │
└──────┬─────┘  └──────┬─────┘   └──────┬─────┘
       └───────────────┴────────────────┘
                       ▼
              ┌─────────────────┐
              │    Response     │
              └─────────────────┘
```

**Rapport avec l'existant :**
- `detected_language` **réutilise** `derive_response_language_trace` (lecture seule) — pas de logique langue dupliquée.
- `requires_tool` / `requires_human_review` pointent vers `COCO_TOOL_CONTRACT_REGISTRY.md` (HITL sur `write`/`external`).
- Aujourd'hui le runtime n'a pas d'Orchestrator dédié (cf. `COCO_AGENTIC_ORCHESTRATION.md` §3) : l'Intent Guard arriverait **avant** `assemble_chat_generation_inputs` une fois implémenté.

---

## 7. Implémentation progressive recommandée

| Phase | Contenu | Touche du code ? |
|-------|---------|------------------|
| **Phase 0** | **Doc only** (ce fichier) — spec, contrat, intentions, forbidden inferences | Non |
| **Phase 1** | **Tests comportementaux** sur prompts sensibles (assertions sur l'intention attendue, pas sur le texte LLM) | Tests only |
| **Phase 2** | Helper **pur** `classify_input_intent(message, language_trace) -> InputUnderstandingResult` — déterministe, sans LLM, sans effet de bord | Nouveau module isolé |
| **Phase 3** | Intégration **légère** dans le chat handler : calcul de l'objet + log/trace, **sans** changer la réponse | `app/api/chat.py` (léger, sous GO) |
| **Phase 4** | **Intent router** complet : `response_mode` influence réellement la consigne système bornée | Sous GO dédié |
| **Phase 5** | **Tool / HITL routing** : `requires_tool` / `requires_human_review` branchés au registre + gate HITL | Sous GO + Phase 2 agentique |

**Règle :** chaque phase exige un **GO explicite**. Aucune phase ne lève les NO GO absolus (§8).

### Esquisse de signature (Phase 2 — NON implémentée)

```python
# Spécification seulement — ne pas créer ce module maintenant.
def classify_input_intent(
    message: str,
    *,
    language_trace: dict,          # issu de derive_response_language_trace (lecture seule)
    project_hint: str = "",
) -> "InputUnderstandingResult":
    """Pur, déterministe, sans LLM ni I/O. Heuristiques lexicales + règles forbidden_inferences."""
    ...
```

---

## 8. NO GO absolus

| Interdit | Détail |
|----------|--------|
| **Code runtime** | Pas de module Intent Guard implémenté en Phase 0 |
| **main / prod** | Doc et staging sandbox seulement |
| **LUTHOR** | Hors scope ; sa mention ne déclenche aucune intégration (FI-3) |
| **Phase 2 ProviderManager** | Non concernée |
| **`app/llm/*`** | Non touché (sauf nécessité clairement justifiée et GO explicite) |
| **`static/index.html`** | Non touché |
| **Patch langue UI** | Langue reste pilotée par `language_policy.py` ; Intent Guard ne la modifie pas |
| **MCP runtime** | Aucun |
| **Restaurant SQL** | Aucun |
| **AFFiNE sync** | Aucun |
| **Tool execution réelle** | Aucune ; `requires_tool` est un signal, pas une exécution |

---

## Références

| Document | Lien |
|----------|------|
| Orchestration & compartiments | `docs/COCO_AGENTIC_ORCHESTRATION.md` |
| Tool Contract Registry | `docs/COCO_TOOL_CONTRACT_REGISTRY.md` |
| Politique de langue (runtime) | `app/core/language_policy.py` |
| API staging | `docs/API_STABILIZATION_V11_7.md` |

---

*Document créé en mode DOC ONLY — Input Understanding Guard spec (Phase 0). Aucun changement runtime.*
