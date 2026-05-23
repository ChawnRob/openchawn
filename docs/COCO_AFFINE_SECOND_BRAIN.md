# COCO — AFFiNE Second Brain (local-first)

SECOND BRAIN in the COCO UI opens the user's **AFFiNE** workspace. It is **not** OpenChawn cloud storage.

## Data principle

AFFiNE Second Brain is **user-owned**. By default, users store their workspace **locally** (desktop) or in an AFFiNE environment they choose (cloud/self-host). OpenChawn/COCO does **not** claim to store user documents by default.

## Frontend configuration (optional)

Set on `window` before or when `static/index.html` loads (e.g. inline script in host page, or future server inject):

| Variable | Purpose |
|----------|---------|
| `OPENCHAWN_AFFINE_LOCAL_URL` | Preferred AFFiNE **local/desktop** URL or deep link when available |
| `OPENCHAWN_AFFINE_URL` | AFFiNE cloud or self-hosted workspace URL |

Per-button override: `data-affine-url` on Second Brain controls.

**Resolution order:** `OPENCHAWN_AFFINE_LOCAL_URL` → `OPENCHAWN_AFFINE_URL` → `data-affine-url` → `https://app.affine.pro`

Example (local dev):

```html
<script>
  window.OPENCHAWN_AFFINE_LOCAL_URL = 'http://localhost:3010';
</script>
```

Env-style placeholders for operators (not read by backend today):

```bash
OPENCHAWN_AFFINE_LOCAL_URL=
OPENCHAWN_AFFINE_URL=
```

## UX copy (do not change without product review)

- Toast on open: *Opening AFFiNE Second Brain. Your workspace stays under your control.*
- Do **not** use: "AFFiNE is connected", "OpenChawn stores your documents", "Memory sync is active"

## Future bridge (TODO in `static/index.html`)

- Desktop/local workspace preference
- Optional self-host URL
- Explicit user consent before any sync
- No OpenChawn document storage by default
- Backend bridge only for retrieval/indexing if the user enables it
