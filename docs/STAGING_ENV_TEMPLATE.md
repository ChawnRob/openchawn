# Staging Environment Variables Template

**Service:** `openchawn-staging` (Railway)  
**Branch:** `sandbox/staging-v11-7`

Copy these into Railway **staging service variables only**.  
**Never commit real secrets.** Replace every `REPLACE_ME` with staging values.

Production variables must **not** be edited using this file without explicit human approval.

---

## Core / environment

```bash
# Not production — keeps .env file loading allowed in dev-like modes
OPENCHAWN_ENV=staging

# Human-readable label (optional; app uses OPENCHAWN_ENV for is_production)
ENVIRONMENT=staging

# JWT signing — use a unique staging secret, not production
SECRET_KEY=REPLACE_ME_STAGING_SECRET_64_CHARS_MIN
OPENCHAWN_SECRET_KEY=REPLACE_ME_STAGING_SECRET_64_CHARS_MIN

LOG_LEVEL=INFO

# Railway sets PORT automatically; do not override unless debugging
# PORT=8000
```

---

## Language / owner (staging-safe defaults)

```bash
# Auto language: leave fixed language empty (runtime auto-detect)
# RESPONSE_LANGUAGE_MODE=auto  → operational equivalent: do not set OPENCHAWN_CHAT_FIXED_LANGUAGE
OPENCHAWN_CHAT_FIXED_LANGUAGE=

# No owner bypass on staging unless testing owner flows
# OWNER_MODE=false  → operational equivalent: leave owner token empty
OPENCHAWN_OWNER_TOKEN=
```

---

## URLs / CORS (update after Railway assigns staging URL)

```bash
APP_BASE_URL=https://REPLACE_ME-openchawn-staging.up.railway.app
FRONTEND_URL=https://REPLACE_ME-openchawn-staging.up.railway.app
OPENCHAWN_CORS_ORIGINS=https://REPLACE_ME-openchawn-staging.up.railway.app,http://127.0.0.1:8000
CORS_ORIGINS=https://REPLACE_ME-openchawn-staging.up.railway.app,http://127.0.0.1:8000
```

Optional future domain:

```bash
# APP_BASE_URL=https://staging.openchawn.com
# FRONTEND_URL=https://staging.openchawn.com
# OPENCHAWN_CORS_ORIGINS=https://staging.openchawn.com,http://127.0.0.1:8000
```

---

## Database / memory (isolate from production)

```bash
OPENCHAWN_DB_PATH=/data/openchawn-staging.db
DATABASE_URL=REPLACE_ME_STAGING_DATABASE_URL_IF_USING_POSTGRES

MEMORY_BACKEND=json
MEMORY_DB_URL=
OPENCHAWN_MEMORY_DIR=/data/memory-staging
MEMPALACE_PATH=/data/mempalace-staging/memories.json
REDIS_URL=

OPENCHAWN_QEI_DIR=/data/qei-staging
```

---

## Rate limits / guest

```bash
GUEST_DAILY_MESSAGE_LIMIT=20
OPENCHAWN_GUEST_DAILY_LIMIT=20
OPENCHAWN_RATE_CHAT=30
OPENCHAWN_RATE_AUTH=10
OPENCHAWN_MAX_MSG_LEN=4000
OPENCHAWN_JWT_HOURS=24
OPENCHAWN_PROFILE=default
```

---

## Provider selection

```bash
DEFAULT_PROVIDER=deepseek
MODEL_PROVIDER=openrouter
OPENCHAWN_PROVIDER=auto
OLLAMA_ENABLED=false
```

---

## LLM API keys (staging keys only — placeholders)

```bash
DEEPSEEK_API_KEY=REPLACE_ME
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com

OPENROUTER_API_KEY=REPLACE_ME
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/auto

OPENAI_API_KEY=REPLACE_ME
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1

MISTRAL_API_KEY=REPLACE_ME
MISTRAL_MODEL=mistral-small-latest
MISTRAL_BASE_URL=https://api.mistral.ai/v1

MINIMAX_API_KEY=REPLACE_ME
MINIMAX_MODEL=MiniMax-M2.7
MINIMAX_BASE_URL=https://api.minimax.io/v1

MOONSHOT_API_KEY=REPLACE_ME
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
MOONSHOT_MODEL=moonshot-v1-8k

KIMI_API_KEY=REPLACE_ME
KIMI_MODEL=kimi-k2-0905-preview
KIMI_BASE_URL=https://api.moonshot.ai/v1

ANTHROPIC_API_KEY=REPLACE_ME
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

INFOMANIAK_API_KEY=REPLACE_ME
INFOMANIAK_MODEL=REPLACE_ME
INFOMANIAK_BASE_URL=REPLACE_ME

QWEN_API_KEY=REPLACE_ME
QWEN_MODEL=qwen-max

PERPLEXITY_API_KEY=REPLACE_ME
PERPLEXITY_MODEL=llama-3.1-sonar-large-128k-online

# Optional / diagnostic
EURIA_API_KEY=REPLACE_ME
EURIA_PROVIDER=REPLACE_ME
```

Aliases also supported by code (use one canonical name per provider):

```bash
# DEEPSEEK_KEY=REPLACE_ME
# DEEPSEEK_TOKEN=REPLACE_ME
# OPEN_ROUTER_API_KEY=REPLACE_ME
```

---

## Optional rules / paths

```bash
INITIAL_RULES_PATH=
RULES_PATH=
SYSTEM_RULES_PATH=
OPENCHAWN_RULES=
SYSTEM_PROMPT_PATH=
CONFIG_PATH=
```

---

## Railway-injected (usually automatic — do not duplicate in docs)

These are set by Railway at runtime; listed for awareness only:

```bash
# RAILWAY_ENVIRONMENT=production
# RAILWAY_PROJECT_ID=<set-by-railway>
# PORT=<set-by-railway>
```

---

## Minimum staging set (if trimming)

At minimum for a working staging chat:

1. `OPENCHAWN_ENV=staging`
2. `SECRET_KEY` / `OPENCHAWN_SECRET_KEY` (unique)
3. `OPENCHAWN_CORS_ORIGINS` + `APP_BASE_URL` (staging URL)
4. At least one LLM key: `DEEPSEEK_API_KEY` or `OPENROUTER_API_KEY`
5. `DEFAULT_PROVIDER` matching configured key
6. Isolated `OPENCHAWN_DB_PATH` or `DATABASE_URL`

---

## Checklist before saving variables

- [ ] Variables pasted into **`openchawn-staging`** only
- [ ] Production service **not** opened for bulk edit
- [ ] No secrets committed to git
- [ ] Staging URL reflected in CORS and `APP_BASE_URL`
