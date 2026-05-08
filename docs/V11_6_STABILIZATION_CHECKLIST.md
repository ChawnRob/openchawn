# OpenChawn V11.6 — stabilization checklist

This document is meant for engineers validating a production rollout. It summarizes the chat pipeline order, observability knobs, smoke tiers, and post-deploy verification.

## Chat pipeline ordering (`handle_chat_request` + `assemble_chat_generation_inputs`)

1. Quota / auth (guest sessions only consume quota via `check_guest_quota`).
2. Language policy (`derive_response_language_trace` → `detect_surface_language`, translation/explicit/fixed/auto) plus `build_language_instruction` appended later in the outbound user blob.
3. Memory retrieval (`build_layered_memory_context`).
4. Runtime language guard (`sanitize_provider_prompts` on combined system + user payload).
5. Provider call (`generate_response` gateway).
6. Post-generation violation guard (`assistant_reply_violates_english_user_expectation` + optional regeneration — first answer is discarded, not persisted).
7. Persistence (`write_exchange`) only once a final textual answer succeeds (HTTP path returns 200 with non-empty output).

## `response_language_mode`

| Mode | Meaning |
|------|---------|
| `auto` | No explicit constraint; output language follows dominant surface detection (`und` maps to English, not French-by-default). |
| `explicit` | User asked for a specific language explicitly (non-translation phrasing detected by regexes). |
| `translate` | Translation-to-target pattern detected (`detect_explicit_language_request` kind `translation_target`). |
| `fixed` | Ops-only pin via `OPENCHAWN_CHAT_FIXED_LANGUAGE` env (normalized language code); keep unset unless needed for deterministic debugging on a sandbox. |

## Debug query (`?debug=true` on `/chat` and `/api/chat`)

Safe diagnostic fields appended to JSON when `debug=true`:

- `route_used` (`POST /chat` or `POST /api/chat`)
- `handler_used` (always `handle_chat_request`)
- `response_language_mode`, `detected_language`, `final_language`, `language_source`
- `forced_french_runtime_detected`, `forced_french_runtime_removed` (assembled + gateway)
- `english_violation_regenerated`
- `deployed_commit` when `RAILWAY_GIT_COMMIT_SHA`/`GIT_COMMIT_SHA`/similar is populated

Prompt text and secrets never appear here.

## Static frontend contract

The production UI ships `static/index.html` calling `fetch(API + '/chat', ...)`. Alias `POST /api/chat` shadows the identical handler only for curls/integrations tests.

## Tests (local scripts)

Run from repo root (`openchawn`):

```bash
./.venv/bin/python scripts/test_chat_route_contract_v116.py
./.venv/bin/python scripts/test_runtime_chat_language_path.py
./.venv/bin/python scripts/test_smoke_test_prod_v116.py
```

## Production smoke tiers (`scripts/smoke_test_prod_v116.py`)

- **SETUP**: `POST /guest/session`
- **CRITICAL**: `GET /health`, `POST /chat`, `POST /api/chat`
- **IMPORTANT**: `GET /health/providers`, `GET /health/language`
- **OPTIONAL**: memory + decision tooling endpoints (`/memory/**`, `/decision/**`, dry-run)

`prod_green=true` iff every **SETUP** and **CRITICAL** row finishes `GREEN`. Warning/failure tiers below CRITICAL never flip `prod_green` by themselves.

## Post-Railway

1. Wait for Railway deploy **SUCCESS**.
2. `python scripts/smoke_test_prod_v116.py --base-url https://www.openchawn.com`
3. Optional: authenticated curl with guest session (`X-Guest-Session`) hitting `/chat?debug=true` vs `/api/chat?debug=true`, verifying identical handler metadata (`handler_used`).
4. Manually sanity-check UI English prompt still answers in English on the hosted site.
