# Staging Environment Variables Template

**Railway service:** `openchawn-staging`  
**Branch:** `sandbox/staging-v11-7`  
**Never commit real secrets.** Replace all `REPLACE_ME` values in Railway UI only.

---

## Policy notes (read first)

1. **Staging variables must be separate from production variables.**  
   Do not point staging at production database, secrets, or domains.

2. **Anthropic must remain optional/dormant unless explicitly enabled.**  
   The app has **no** `anthropic_provider` wired to `/chat`. Setting `ANTHROPIC_API_KEY` on staging has **no effect** today.  
   **Do not add Anthropic keys to Railway production.**

3. **Do not copy production `.env` or Railway prod variables into staging.**

---

## Required staging template (placeholders)

```bash
# ── Core ──
ENVIRONMENT=staging
OPENCHAWN_ENV=staging

RESPONSE_LANGUAGE_MODE=auto
# Operational: leave OPENCHAWN_CHAT_FIXED_LANGUAGE unset for auto-detect

OWNER_MODE=false
# Operational: leave OPENCHAWN_OWNER_TOKEN empty unless testing owner flows

LOG_LEVEL=info

# ── Security / CORS ──
JWT_SECRET=REPLACE_ME
# App also accepts: SECRET_KEY=REPLACE_ME  OPENCHAWN_SECRET_KEY=REPLACE_ME (use same staging value)

ALLOWED_ORIGINS=REPLACE_ME_STAGING_URL
# App reads: OPENCHAWN_CORS_ORIGINS or CORS_ORIGINS (comma-separated). Example:
# ALLOWED_ORIGINS=https://your-staging.up.railway.app,http://127.0.0.1:8000

# ── Database (isolated from production) ──
DATABASE_URL=REPLACE_ME
OPENCHAWN_DB_PATH=/data/openchawn-staging.db

# ── Rate limiting ──
RATE_LIMIT_ENABLED=true
# Note: middleware is active in app; this flag is documentation-only unless wired later.

# ── LLM providers (staging keys only) ──
DEFAULT_PROVIDER=deepseek

DEEPSEEK_API_KEY=REPLACE_ME
DEEPSEEK_MODEL=deepseek-v4-pro

OPENAI_API_KEY=REPLACE_ME

OPENROUTER_API_KEY=REPLACE_ME
OPENROUTER_MODEL=openrouter/auto

MISTRAL_API_KEY=REPLACE_ME
# Mistral module exists but is not in main chat registry — optional for future use.

# ── Optional / dormant (do not enable on production) ──
ANTHROPIC_API_KEY=REPLACE_ME_OPTIONAL_DISABLED
# DORMANT: not wired to ProviderManager or gateway. Leave empty unless implementing Anthropic.

OLLAMA_BASE_URL=REPLACE_ME_OPTIONAL_LOCAL_ONLY
# LOCAL ONLY: Ollama is disabled in production chat (OLLAMA_ENABLED=false). Do not use on Railway staging unless explicitly testing.

# ── URLs (set after Railway assigns staging hostname) ──
APP_BASE_URL=REPLACE_ME_STAGING_URL
FRONTEND_URL=REPLACE_ME_STAGING_URL

# ── COCO Second Brain → AFFiNE (frontend window.* — optional) ──
# Not backend secrets. Inject via host page script if needed.
# OPENCHAWN_AFFINE_LOCAL_URL=   # preferred local/desktop AFFiNE URL or deep link
# OPENCHAWN_AFFINE_URL=        # cloud or self-host workspace fallback
# Data principle: AFFiNE workspace is user-owned; OpenChawn does not store documents by default.
# See docs/COCO_AFFINE_SECOND_BRAIN.md
```

---

## Extended optional variables (same staging service)

Use only if needed; still **staging-only** values.

```bash
KIMI_API_KEY=REPLACE_ME
INFOMANIAK_API_KEY=REPLACE_ME
INFOMANIAK_MODEL=REPLACE_ME
INFOMANIAK_BASE_URL=REPLACE_ME

GUEST_DAILY_MESSAGE_LIMIT=20
OPENCHAWN_RATE_CHAT=30
OPENCHAWN_RATE_AUTH=10
OPENCHAWN_MAX_MSG_LEN=4000

MEMORY_BACKEND=json
OPENCHAWN_MEMORY_DIR=/data/memory-staging
```

---

## Minimum set for a working staging chat

1. `ENVIRONMENT=staging` / `OPENCHAWN_ENV=staging`
2. `JWT_SECRET` (or `SECRET_KEY`) — unique, not production
3. `ALLOWED_ORIGINS` = staging public URL
4. `DATABASE_URL` or `OPENCHAWN_DB_PATH` — **not** production data
5. At least one LLM key: `DEEPSEEK_API_KEY` and/or `OPENROUTER_API_KEY`
6. `DEFAULT_PROVIDER` matching the key you configure

---

## Checklist before saving in Railway

- [ ] Variables saved on **`openchawn-staging` only**
- [ ] Production service variables **not** opened for edit
- [ ] `ANTHROPIC_API_KEY` left empty or explicitly marked disabled
- [ ] No Anthropic keys on **production**
- [ ] `ALLOWED_ORIGINS` uses **staging URL**, not `openchawn.com` / `www.openchawn.com`
- [ ] No secrets committed to git
