# CLAUDE.md

## What this is
LLM chatbot: React frontend, FastAPI backend, SQLite storage, LiteLLM for
completions with a multi-key pool, automatic failover, and response caching.
Assignment contract is fixed — field names, paths and testids are not negotiable.

## Hard rules
1. **Never rename a contract field.** Endpoints are exactly `GET /health`,
   `POST /chat`, `GET /sessions/{session_id}/messages`. Metadata keys are exactly
   `resolution_source`, `model`, `latency_ms`, `input_tokens`, `output_tokens`,
   `key_id`, `fallback_attempts`. Extra fields are allowed; missing/renamed are not.
2. **Never leak a key.** `key_id` is `key_1`, `key_2`, ... Never the key material.
   Never log the key. Never return it in an error. `/health` returns a count only.
3. **No stack traces, no HTML errors.** Every error is JSON with a `detail` field.
   A global exception handler turns anything unexpected into
   `500 {"detail": "internal error"}`.
4. **Failed requests do not touch history.** On 422 or 503, nothing is written to
   SQLite — not the user message, not a partial assistant row.
5. **Tokens are per request, never cumulative.** `input_tokens` is prompt tokens
   for this call (system + history + new message). `output_tokens` is this reply only.
6. **SQLite only.** No Redis, no Postgres. Cache is LiteLLM's in-memory cache
   (the disk backend was removed from LiteLLM; `litellm` is pinned to 1.77.7).
7. **Config only via env vars.** No hardcoded URLs, ports, models or keys.
8. **Simulation is gated.** `X-Simulate-Failure` is honored only when
   `ENABLE_FAILURE_SIMULATION=true`; otherwise the header is ignored silently.

## Code style
- Simple and readable over clever. Small functions, explicit names, no metaclasses,
  no dependency-injection frameworks, no premature abstraction.
- Type hints on function signatures. Pydantic models for request/response.
- One concern per module. If a file passes ~200 lines, split it.
- Comments explain *why*, not *what*.
- Frontend: function components + hooks. No Redux, no component library required.

## Layout
```
/backend
  app/
    main.py        # FastAPI app, routes, CORS, exception handlers
    config.py      # env parsing -> Settings
    schemas.py     # pydantic request/response models
    db.py          # sqlite connection, schema init, message read/write
    llm.py         # LiteLLM call, key pool, failover loop, cache labelling
    simulate.py    # X-Simulate-Failure header parsing
  tests/
  Dockerfile
  requirements.txt
/frontend
  src/
    App.jsx
    api.js
    components/{MessageList,MessageInput,MetadataBar}.jsx
  Dockerfile
  nginx.conf
docker-compose.yml
Makefile
.env.example
README.md
```

## Definition of done for any change
- `pytest` green (offline — tests stub the provider via LiteLLM `mock_response`).
- `curl` the three endpoints by hand; shapes match the contract.
- `make up` boots; frontend at :3000 talks to backend at :8000.
- No key material anywhere in logs, responses or the repo.
