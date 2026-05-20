# Railway Staging Setup — OpenChawn

**Source of truth:** `/Users/chawn-mbp-15/projects/openchawn`  
**Staging branch:** `sandbox/staging-v11-7`  
**Production branch:** `main` (must stay untouched during staging setup)

This document is **instructions only**. It does not deploy anything automatically.

---

## Deployment structure (repo)

| Item | Value |
|------|--------|
| **Package manager** | `pip` + `requirements.txt` (no root `package.json`) |
| **Runtime** | Python 3.x (match local `.venv`, currently 3.14.x locally) |
| **Start command** | `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` (see `Procfile`) |
| **Build command** | None required — Railway/Nixpacks installs deps from `requirements.txt` |
| **Entrypoints** | `Procfile` (Railway), `main.py` (alternate wrapper) |
| **Backend** | `app/` — FastAPI (`app.main:app`) |
| **Frontend** | `static/index.html` served at `/` and `/static` |
| **Railway config in repo** | `Procfile` only (no `railway.toml` in tree) |

---

## Service naming

| Service | Recommendation | Rule |
|---------|----------------|------|
| **Staging** | `openchawn-staging` | New service; deploy from `sandbox/staging-v11-7` |
| **Production** | existing production service (e.g. current OpenChawn prod) | **Do not modify** branch, variables, or domain without explicit approval |

---

## URLs and domains

| Environment | URL |
|-------------|-----|
| **Staging (Railway default)** | `https://<openchawn-staging>.up.railway.app` (assigned by Railway) |
| **Staging (optional future)** | `staging.openchawn.com` — DNS CNAME only after staging smoke passes |
| **Production** | `https://www.openchawn.com` — **never point production DNS to staging** |

**Warning:** Never point the production domain (`www.openchawn.com`) at the staging service. Staging uses a **separate** Railway service and **separate** variable set.

---

## Railway setup checklist

Complete in the Railway dashboard (human operator).

### A. Create staging service (do not touch production)

- [ ] In the OpenChawn Railway project, **Add service** → name: **`openchawn-staging`**
- [ ] Connect GitHub repo: `ChawnRob/openchawn`
- [ ] Set **branch** to: `sandbox/staging-v11-7` (not `main`)
- [ ] Confirm **root directory** is repo root `/`
- [ ] Confirm start command matches `Procfile`:  
      `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Leave **production service** settings unchanged

### B. Staging variables (separate from production)

- [ ] Open **Variables** on **`openchawn-staging` only**
- [ ] Copy structure from `docs/STAGING_ENV_TEMPLATE.md` (placeholders → real staging values)
- [ ] Use **`OPENCHAWN_ENV=staging`** or `development` (not `production` unless intentional)
- [ ] Set **`OPENCHAWN_CORS_ORIGINS`** to the staging Railway URL (and local dev if needed)
- [ ] Set **`APP_BASE_URL`** / **`FRONTEND_URL`** to staging URL when known
- [ ] Use **staging-only** API keys or low-quota keys where possible
- [ ] **Do not** copy production secrets into a shared doc or commit
- [ ] **Do not** edit production service variables in this step

### C. Data isolation

- [ ] Prefer a **separate** `OPENCHAWN_DB_PATH` or staging `DATABASE_URL` (do not share prod DB)
- [ ] Prefer separate memory paths / `MEMORY_BACKEND=json` with staging volume if applicable
- [ ] Confirm guest quota limits are acceptable for staging (`GUEST_DAILY_MESSAGE_LIMIT`)

### D. First deploy (staging only)

- [ ] Trigger deploy on `openchawn-staging` from `sandbox/staging-v11-7`
- [ ] Wait for build + deploy green
- [ ] Open staging public URL — homepage loads

### E. Optional custom domain (later)

- [ ] Add `staging.openchawn.com` in Railway → staging service only
- [ ] DNS CNAME to Railway target
- [ ] Update `OPENCHAWN_CORS_ORIGINS` and `APP_BASE_URL` to include `https://staging.openchawn.com`
- [ ] Re-run smoke tests

---

## Smoke test after staging deploy

Use `docs/SMOKE_TEST_CHECKLIST.md` against the **staging URL** (not production).

Minimum:

1. Staging URL returns **200** on `/`
2. OpenChawn / COCO UI loads
3. Send one English message — reply in English (no forced French)
4. Mobile width (≤640px) — composer OK, emblem hidden on mobile
5. Desktop width (≥641px) — no grid bug, cockpit visible if merged
6. Browser console — no critical errors
7. **`www.openchawn.com`** still serves production build (unchanged)

---

## Rollback rule

| Layer | Rollback |
|-------|----------|
| **Production** | Redeploy last stable tag on `main` (e.g. `v11.6.3-stable`, `v11.7-ux`) or revert merge on `main` |
| **Staging** | Redeploy previous staging commit or disable `openchawn-staging` service |
| **Git** | `main` remains production; staging experiments stay on `sandbox/staging-v11-7` until PR merge |

Production can always be restored from the **last stable tag** on `main`. Staging failures must not require production changes.

---

## Related docs

- `docs/SANDBOX_WORKFLOW.md`
- `docs/SMOKE_TEST_CHECKLIST.md`
- `docs/DEPLOYMENT_RULES.md`
- `docs/STAGING_ENV_TEMPLATE.md`
