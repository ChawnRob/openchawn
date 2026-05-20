# Railway Staging Setup — OpenChawn

**Source of truth:** `/Users/chawn-mbp-15/projects/openchawn`  
**GitHub:** `ChawnRob/openchawn`  
**Staging branch:** `sandbox/staging-v11-7`  
**Production branch:** `main` (production only — do not deploy experiments here)

This document is **instructions only**. Cursor/docs workflow only — no automatic deploy.

---

## Service model

| Service | Name | Branch | Domain / URL |
|---------|------|--------|----------------|
| **Staging** | `openchawn-staging` | `sandbox/staging-v11-7` | Separate Railway URL (e.g. `https://<service>.up.railway.app`) |
| **Production** | existing prod service | `main` | `https://www.openchawn.com` — **must remain untouched** |

**Optional future staging domain:** `staging.openchawn.com` (CNAME → staging service only, after smoke tests pass).

---

## Critical warnings

1. **Never point `openchawn.com` or `www.openchawn.com` to staging.**  
   Production DNS must stay on the **production** Railway service only.

2. **Never edit Railway production variables** during staging setup.

3. **Staging variables must be a separate set** on `openchawn-staging` — do not share production DB, secrets, or API keys.

4. **Do not merge `sandbox/staging-v11-7` into `main`** until PR review + staging smoke pass.

---

## Repo deployment structure (reference)

| Item | Value |
|------|--------|
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (`Procfile`) |
| Build | Nixpacks / `pip install -r requirements.txt` |
| Backend | `app/` (FastAPI) |
| Frontend | `static/index.html` at `/` |

---

## Railway staging setup checklist

### 1. Create staging service (production untouched)

- [ ] Railway project → **Add service** → name: **`openchawn-staging`**
- [ ] Connect repo: `ChawnRob/openchawn`
- [ ] **Do not** change production service name, branch, or domains

### 2. Required branch connection

- [ ] **Deploy branch:** `sandbox/staging-v11-7` (not `main`)
- [ ] Root directory: `/` (repo root)
- [ ] Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Confirm auto-deploy is **only** for this branch on **this** service

### 3. Required environment variable separation

- [ ] Open **Variables** tab on **`openchawn-staging` only**
- [ ] Paste from `docs/STAGING_ENV_TEMPLATE.md` (replace placeholders)
- [ ] Use **staging-only** `DATABASE_URL` / DB path (never production DB)
- [ ] Use **staging-only** JWT/secret (`JWT_SECRET` / `SECRET_KEY` — unique value)
- [ ] Set `ALLOWED_ORIGINS` / CORS to **staging URL only** (+ local dev if needed)
- [ ] **Do not** copy production variable values in bulk
- [ ] **Do not** add Anthropic keys to production (Anthropic is dormant in app — see env template)

### 4. Staging URL (separate from production)

- [ ] Note Railway-generated URL: `https://<openchawn-staging>.up.railway.app`
- [ ] Verify it is **not** `www.openchawn.com`
- [ ] Update staging env: `APP_BASE_URL`, `FRONTEND_URL`, `ALLOWED_ORIGINS` with this URL

### 5. First deploy (staging only)

- [ ] Deploy `openchawn-staging` from `sandbox/staging-v11-7`
- [ ] Build succeeds, service healthy
- [ ] `GET /` returns 200 on staging URL

### 6. Optional: `staging.openchawn.com` (later)

- [ ] Add custom domain on **staging service only**
- [ ] DNS CNAME to Railway
- [ ] Update CORS / `ALLOWED_ORIGINS` to include `https://staging.openchawn.com`
- [ ] Re-run smoke tests

---

## Smoke test checklist (before PR to `main`)

Run on **staging URL only**. Production must stay unchanged.

| # | Check | PASS |
|---|--------|------|
| 1 | Staging homepage loads (`/`) | |
| 2 | OpenChawn / COCO UI visible | |
| 3 | Message input + send works | |
| 4 | Provider response returns (configured LLM key) | |
| 5 | Language auto — English in → English out (no forced French) | |
| 6 | Mobile ≤640px — composer OK, no major regression | |
| 7 | Desktop ≥641px — no grid bug (if V11.7 UX merged) | |
| 8 | No critical browser console errors | |
| 9 | `www.openchawn.com` still production (spot-check) | |
| 10 | `pytest -q` + language smoke passed locally on same commit | |

Full detail: `docs/SMOKE_TEST_CHECKLIST.md`

**Do not open PR to `main` until staging smoke passes.**

---

## Rollback rule

| Environment | Rollback action |
|-------------|-----------------|
| **Production** | Redeploy last **stable tag** on `main` (e.g. `v11.6.3-stable`, `v11.7-ux`) or revert merge commit |
| **Staging** | Redeploy previous staging commit or pause `openchawn-staging` |
| **Git** | `main` stays production; staging work stays on `sandbox/staging-v11-7` until approved PR |

Production can always be restored from the **last stable tag**. Staging failures must not force production changes.

---

## Related docs

- `docs/STAGING_ENV_TEMPLATE.md`
- `docs/SANDBOX_WORKFLOW.md`
- `docs/SMOKE_TEST_CHECKLIST.md`
- `docs/DEPLOYMENT_RULES.md`
