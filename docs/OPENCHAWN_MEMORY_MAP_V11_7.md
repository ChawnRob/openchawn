# OpenChawn Memory Map V11.7

This file is the source of truth for V11.7 memory routing in OpenChawn.

If the official chat memory path changes, update this file in the same change.

## Official Current Chat Memory Path

For V11.7, the official production chat memory path is the fractal memory stack behind `POST /chat`.

Official request path:

1. HTTP entry in `app/main.py` via the chat router from `app/api/chat.py`
2. Prompt assembly in `app/api/chat.py`
3. Memory read in `app/memory/fractal_memory.py`
4. Provider call in `app/api/chat.py`
5. Memory write in `app/memory/fractal_memory.py`

This is the only memory routing path that should be treated as the main chat runtime unless another path is explicitly wired and this document is updated.

## Exact Files Involved

Primary official runtime files:

- `app/main.py`
- `app/api/chat.py`
- `app/memory/fractal_memory.py`

Supporting official memory files used by the fractal path:

- `app/memory/faiss_memory.py`
- `app/memory/retrieval_policy.py`

Key runtime touchpoints:

- `app/main.py`: mounts the chat router
- `app/api/chat.py`: assembles the outbound prompt and calls the official memory read/write functions
- `app/memory/fractal_memory.py`: implements the official read path via `build_layered_memory_context()` and the official write path via `write_exchange()`

## Request Flow

```text
POST /chat
  -> app/main.py
  -> app/api/chat.py
     -> assemble_chat_generation_inputs()
        -> build_layered_memory_context() in app/memory/fractal_memory.py
     -> provider call
     -> write_exchange() in app/memory/fractal_memory.py
  -> HTTP response
```

## Current Storage Reality

The active official memory path uses the backend selected inside `app/memory/fractal_memory.py`.

| `MEMORY_BACKEND` | Use case | Durable |
|------------------|----------|---------|
| `json` (default) | Local development only | No — file at `data/memory/fractal_memory.json` |
| `postgres` | Railway / production chat memory | Yes — table `fractal_memories` |

### Environment variables

- `MEMORY_BACKEND` — `json` or `postgres`
- `MEMORY_DB_URL` — preferred Postgres URL for fractal memory (overrides `DATABASE_URL`)
- `DATABASE_URL` — fallback when `MEMORY_DB_URL` is unset
- `MEMORY_ALLOW_EPHEMERAL_JSON` — set `true` only if production must temporarily use ephemeral JSON (not recommended)

Production rules:

- `OPENCHAWN_ENV=production` with `MEMORY_BACKEND=postgres` requires `MEMORY_DB_URL` or `DATABASE_URL`
- Do not rely on local JSON on Railway — containers are ephemeral
- `GET /api/memory/runtime-status?verify=true` sets `memory_read_write_verified` only after a real Postgres read/write probe

### Postgres schema (`fractal_memories`)

Indexed columns: `id`, `timestamp`, `memory_type`, `memory_level`, `project_name`, `user_id`, plus message fields and `tags` / `children_ids` / `metadata` JSONB.

Full round-trip fidelity: `entry_payload` JSONB stores the complete normalized fractal entry (lifecycle, decay, concept merge metadata, etc.).

Auth SQLite (`OPENCHAWN_DB_PATH`) remains separate from fractal chat memory.

## Warning: Parallel Memory Families Are Not Official Chat Runtime

The following areas may exist in the repository, but they are not the official V11.7 main chat runtime unless explicitly wired later:

- `app/memory.py`
- `app/memory/store.py`
- `app/memory/context.py`
- `app/mempalace/*`
- `app/asi_evolve/*`
- `app/orchestrator.py`
- `app/router.py`
- `routers/memory.py`
- `memory/*`

Treat these as experimental, parallel, legacy, or future-facing layers unless a deliberate runtime migration is performed and this file is updated in the same change.

Do not route `POST /chat` to these families implicitly or by partial refactor.

## Railway production checklist

```bash
MEMORY_BACKEND=postgres
MEMORY_DB_URL=${{Postgres.DATABASE_URL}}   # or reuse service DATABASE_URL
OPENCHAWN_ENV=production
```

Verify after deploy:

```bash
curl -s 'https://www.openchawn.com/api/memory/runtime-status?verify=true'
```

Expect: `fractal_memory_backend=postgres`, `fractal_persistent=true`, `database_provider=postgres`, and `memory_read_write_verified=true` when the DB probe succeeds.

## Future Migration

Durable memory stays behind the official fractal contract (`build_layered_memory_context` / `write_exchange`). Do not route `POST /chat` to parallel memory families without updating this file.

## Change Control Note

Do not change the official chat memory routing without updating this file.

That includes changes to:

- the official read function
- the official write function
- the backend selection strategy
- the files considered part of the production chat memory path

