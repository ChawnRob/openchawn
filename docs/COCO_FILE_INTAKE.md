# COCO File / Image Intake — Specification

**Repo:** OpenChawn (COCO)  
**Branch cible:** `sandbox/staging-v11-7`  
**Statut:** V1 skeleton — intake UI + route minimale, **pas d'analyse IA**  
**Parents:** `docs/COCO_TOOL_CONTRACT_REGISTRY.md`, `docs/COCO_INPUT_UNDERSTANDING_GUARD.md`, `docs/COCO_AGENTIC_ORCHESTRATION.md`  
**Dernière révision doc:** 2026-06-04

---

## 1. But

Préparer COCO pour recevoir des **inputs multimodaux** (photo, capture d'écran, PDF, CSV, texte) dans un cockpit cohérent, sans activer une pipeline d'analyse complexe en V1.

**Principes V1 :**

- L'utilisateur **voit** toujours ce qui est sélectionné (nom, taille).
- Aucun traitement **silencieux**.
- Aucun stockage **durable** automatique.
- Réponse explicite si l'analyse n'est pas encore activée.

---

## 2. Types acceptés

| MIME (prioritaire) | Extensions | Usage V1 |
|--------------------|------------|----------|
| `image/png` | `.png` | Intake OK, analyse Phase 3 |
| `image/jpeg` | `.jpg`, `.jpeg` | Idem |
| `image/webp` | `.webp` | Idem |
| `application/pdf` | `.pdf` | Intake OK, extraction Phase 2 |
| `text/plain` | `.txt` | Intake OK |
| `text/csv` | `.csv` | Intake OK, restaurant Phase 4 |

**Taille max :** **10 MB** (`10_485_760` octets) par fichier.

**Distinct de « Importer du texte » :** le panneau legacy `.txt/.md` (100 Ko, collage dans le message) reste séparé. Le File Intake cible l'analyse multimodale future, pas le collage de prompt.

---

## 3. Flow UI (V1 skeleton)

```text
┌─────────────────────────────────────────┐
│ Composer (inchangé, non masqué)         │
│  [📎 Attach] [🎤] [textarea] [Send]    │
└─────────────────────────────────────────┘
         │ sélection fichier
         ▼
┌─────────────────────────────────────────┐
│ File intake bar (visible si sélection)  │
│  report.png · 1.2 MB                    │
│  File ready for analysis                │
│  [Clear]                                │
└─────────────────────────────────────────┘
         │ Envoyer (avec ou sans texte)
         ▼
   POST /api/files/intake (multipart)
         ▼
   Bulle assistant : message serveur explicite
   (analysis pipeline not enabled yet)
         ▼
   Sélection effacée — pas de stockage durable
```

**Comportement Envoyer :**

1. Si un fichier est en attente → `POST /api/files/intake` d'abord, bulle assistant avec la réponse JSON.
2. Si du texte est aussi présent → `POST /chat` ensuite (flux chat inchangé).
3. Fichier seul sans texte → intake uniquement (pas d'appel LLM).

---

## 4. Flow backend cible

### Route (implémentée en V1 minimal)

| Méthode | Chemin | Auth |
|---------|--------|------|
| `POST` | `/api/files/intake` | `X-Guest-Session` ou Bearer (même que `/chat`) |

**Alias documentaire :** `POST /files/intake` — non exposé en V1 (un seul chemin `/api/files/intake`).

### Corps

- `multipart/form-data`, champ `file` (obligatoire).

### Réponse succès (200)

```json
{
  "ok": true,
  "status": "ready",
  "message": "File intake is ready, analysis pipeline is not enabled yet.",
  "filename": "screenshot.png",
  "size_bytes": 245760,
  "content_type": "image/png",
  "analysis_enabled": false,
  "stored": false,
  "intake_version": "file_intake_v1"
}
```

### Failure modes (normatifs)

| `failure_mode` | HTTP | Signification |
|----------------|------|---------------|
| `file_too_large` | 413 | > 10 MB |
| `unsupported_file_type` | 415 | MIME / extension hors liste |
| `upload_failed` | 400 | Fichier absent ou lecture échouée |
| `extraction_failed` | 422 | Réservé Phase 2 (non utilisé V1) |
| `analysis_not_enabled_yet` | 200 | Statut informatif dans `message` / `analysis_enabled: false` |

Les erreurs renvoient un JSON structuré :

```json
{
  "ok": false,
  "failure_mode": "file_too_large",
  "message": "File exceeds maximum size of 10 MB."
}
```

### Sécurité V1

- Lecture en mémoire **bornée** (max 10 MB + 1 octet pour détection dépassement).
- **Aucun** écriture disque, **aucun** enregistrement fractal_memory.
- Contenu du fichier **non** renvoyé dans la réponse.
- Logs : nom tronqué, taille, MIME — pas de dump binaire.

---

## 5. Routes existantes (audit)

| Route | Rôle | Lien File Intake |
|-------|------|------------------|
| `POST /chat`, `POST /api/chat` | Chat LLM | Inchangé ; texte seul ou après intake |
| Import UI `importFile` | `.txt/.md` → collage message | **Séparé** — pas le File Intake |
| `POST /memory/...` | Mémoire fractale | **Non** utilisé pour fichiers V1 |
| `POST /api/files/intake` | **Nouveau** V1 | Intake skeleton |

Aucune route upload fichier n'existait avant V1.

---

## 6. NO GO (V1)

| Interdit | Détail |
|----------|--------|
| Analyse IA / vision / OCR | Phase 3+ |
| Stockage permanent | Pas de S3, pas de mémoire fichier |
| AFFiNE sync | Aucun |
| MCP runtime | Aucun |
| Restaurant SQL | Phase 4 |
| LUTHOR | Hors scope |
| `app/llm/*` | Non touché |
| ProviderManager | Non touché |
| main / prod | Staging sandbox |
| Patch langue UI | Non mélangé |

---

## 7. Phases futures

| Phase | Contenu | Code ? |
|-------|---------|--------|
| **Phase 0** | UI skeleton + doc (ce livrable) | UI + route minimale |
| **Phase 1** | Upload temporaire (TTL, id intake) | Backend storage éphémère |
| **Phase 2** | Text extraction (PDF, plain) | Workers |
| **Phase 3** | Image / screenshot analysis | Vision tool + HITL |
| **Phase 4** | CSV/Excel restaurant analysis | Data governor |
| **Phase 5** | AFFiNE export with HITL | Tool Contract `create_affine_note` |

Chaque phase exige un **GO explicite**.

---

## 8. Lien Tool Contract (futur)

Intake V1 prépare un futur tool `analyze_uploaded_file` (registre non enregistré) :

- `side_effect_level`: `read` puis `none` pour preview
- analyse destructive / export → HITL

Voir `docs/COCO_TOOL_CONTRACT_REGISTRY.md`.

---

*Document V1 — File Intake skeleton. Staging only.*
