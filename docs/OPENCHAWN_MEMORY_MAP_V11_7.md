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

The active official memory path currently uses the backend selected inside `app/memory/fractal_memory.py`.

Today that means:

- `LocalJsonMemoryBackend` is the practical default path
- `PostgresMemoryBackend` exists as the intended durable production target
- the Postgres path is prepared but not yet the completed durable production source of truth

Important production note:

- local JSON storage is acceptable for local and development usage
- local JSON must not be treated as the final durable production memory backend on Railway

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

## Future Migration

When durable production memory is added later, the migration point should stay inside the official fractal path rather than bypassing it.

Recommended future target:

- keep `app/api/chat.py` as the official chat entrypoint
- keep `build_layered_memory_context()` as the official read boundary
- keep `write_exchange()` as the official write boundary
- add the durable backend behind `app/memory/fractal_memory.py`
- complete `PostgresMemoryBackend` there for Railway production durability
- keep JSON as a local/dev fallback only

In other words, future durability should be added behind the existing official runtime contract, not by silently switching `POST /chat` to a parallel memory family.

## Change Control Note

Do not change the official chat memory routing without updating this file.

That includes changes to:

- the official read function
- the official write function
- the backend selection strategy
- the files considered part of the production chat memory path

