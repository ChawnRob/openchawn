# API stabilization — V11.7 (staging check-up)

Minimal reference for ops smoke tests and Railway stale-deployment verification. No secrets in responses.

## POST /chat

Primary chat entry used by `static/index.html`.

| Item | Value |
|------|-------|
| Auth | Guest: header `X-Guest-Session` (from `POST /guest/session`). Owner: `Authorization: Bearer <OPENCHAWN_OWNER_TOKEN>` when configured. |
| Body | `{"message": "...", "profile": "default", "project_name": "", "provider": ""}` |
| Success | `200` — JSON with `output`, `provider`, optional guest quota fields |
| Provider down | `503` — `detail`: `Provider indisponible: …` (no crash) |
| Guest quota | `429` when daily limit exceeded — header `X-Guest-Quota-Block-Reason` (`daily_limit_exceeded`, `unknown_session`, `ip_mismatch`) |
| Middleware 429 | `Too many requests` — header `X-Rate-Limit-Reason` (`chat_throttle_2s`, `path_rule_60s`) — distinct from guest quota |
| Debug | `?debug=true` adds safe diagnostic fields (no prompt text, no secrets) |

## POST /api/chat

Alias of `POST /chat`. Same handler (`handle_chat_request`), same request/response contract. Use for curl, integrations, and contract tests.

## GET /guest/quota/observability

Staging diagnostics for guest quota (alias: `GET /api/guest/quota/observability`). No secrets.

| Field | Meaning |
|-------|---------|
| `counters` | In-process event counts (`quota_message_ok`, `quota_check_blocked`, `block_reason:*`, …) |
| `summary` | Aggregated allowed/blocked/session totals |
| `live_store` | Active sessions today, sessions at limit, IP fingerprints (hashed) |
| `recent_events` | Last N events with `session_prefix` + `ip_fingerprint` for log correlation |
| `log_correlation_fields` | Suggested Railway/log filter keys |

Query: `?recent=25` (1–100) caps `recent_events` length.

**429 triage:** guest daily limit → French `detail` + `X-Guest-Quota-Block-Reason`. Chat throttle → `Too many requests` + `X-Rate-Limit-Reason`.

## GET /health

Liveness probe.

```json
{
  "mode": "handle",
  "status": "ok",
  "guest_quota": { "guest_limit": 10, "guest_remaining": null, "reset_window": "utc_calendar_day" }
}
```

## GET /__runtime

SRE incident metadata (hidden from OpenAPI schema).

| Field | Meaning |
|-------|---------|
| `git_commit` | Deployed commit (`RAILWAY_GIT_COMMIT_SHA` / `GIT_COMMIT_SHA` when set) |
| `environment` | `OPENCHAWN_ENV` or `RAILWAY_ENVIRONMENT` |
| `language_policy_version` | Active language policy revision |
| `provider_runtime_version` | Provider runtime probe revision |
| `started_at` | Process start timestamp |

Compare `git_commit` to the branch tip you expect on staging.

## GET /health/providers

LLM provider ops snapshot (no API keys).

- `active_provider`, `configured_providers`, `missing_keys`
- `production_safe`, `capabilities`
- `provider_health`, `cost_tracking`, `fallback_recent`

## GET /api/memory/runtime-status

Safe memory/database audit. Optional query: `?verify=true` (isolated read/write probe; Postgres-only durable verify).

Typical fields: `database_configured`, `database_provider`, `fractal_memory_backend`, `short_memory_enabled`, `long_memory_enabled`, `vector_memory_enabled`, `memory_read_write_verified`.

Never returns connection strings, passwords, or raw env secrets.

## Railway stale deployment checklist

1. **Git push landed** — GitHub branch `sandbox/staging-v11-7` shows the expected commit.
2. **Railway build** — Latest deploy succeeded; build log shows `pip install -r requirements.txt`.
3. **Runtime commit** — `GET /__runtime` → `git_commit` matches the pushed SHA (first 7+ chars).
4. **Health** — `GET /health` → `status: ok`.
5. **Providers** — `GET /health/providers` → `configured_providers` / `missing_keys` match staging env vars.
6. **Memory** — `GET /api/memory/runtime-status` → `200`, backend matches `MEMORY_BACKEND` (json vs postgres).
7. **Chat smoke** — `POST /guest/session` then `POST /chat` with a short message returns `200` or explicit `503` (not `500`).
8. **Guest quota observability** — `GET /guest/quota/observability` → `status: ok`; after a forced 429, `block_reason:daily_limit_exceeded` increments.
9. **UI cache** — Hard refresh or private window if static assets look old; API commit from `/__runtime` is the source of truth for backend.

## Dependencies note

Core runtime: `requirements.txt` (FastAPI, uvicorn, httpx, requests, python-dotenv, pydantic, psycopg).

Optional vector layer: `faiss-cpu` and `numpy` are lazy-imported in `app/memory/faiss_memory.py`. Railway deploy works without them; semantic FAISS index falls back to brute-force when unavailable.

Local tests: `pip install -r requirements-dev.txt` then `pytest -q`.
