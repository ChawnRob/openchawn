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

## External open strategy (COCO tab never navigates away)

1. Resolve an **https/http** AFFiNE workspace URL (never assign `window.location` on COCO).
2. If the URL is allowed, build an official **stable** desktop deep link (`affine://…?new-tab=1`, same shape as AFFiNE `getOpenUrlInDesktopAppLink`) and trigger it via a transient `<a>` click (OS opens the desktop app when installed).
3. Toast always offers a **web fallback** link (`target="_blank"`, `rel="noopener noreferrer"`) to the resolved workspace URL.
4. If deep link construction fails, open the web workspace in a separate tab/window via the same anchor pattern and toast: *AFFiNE opened in a separate tab/window. Browser choice is controlled by your system.*
5. No browser-specific hacks (cannot force Chrome vs Safari from a web page).

## UX copy (do not change without product review)

- Desktop attempt: *Opening AFFiNE desktop if installed. Otherwise open the web workspace:*
- Web-only open: *AFFiNE opened in a separate tab/window. Browser choice is controlled by your system.*
- Do **not** use: "AFFiNE is connected", "OpenChawn stores your documents", "Memory sync is active"

## Backend runtime (COCO)

- Module: `app/core/second_brain.py`
- Status: `GET /api/second-brain/status` (safe fields only, no URLs)
- Injected into COCO system prompt via `build_openchawn_base_system_prompt()` in `app/api/chat.py`
- `api_sync_active` is **false** unless `OPENCHAWN_AFFINE_API_SYNC_ACTIVE=true` (explicit opt-in)

## Future bridge (TODO in `static/index.html`)

- Desktop/local workspace preference
- Optional self-host URL
- Explicit user consent before any sync
- No OpenChawn document storage by default
- Backend bridge only for retrieval/indexing if the user enables it
