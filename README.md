# LLM Chatbot: Key Failover & Response Caching

A React chat UI and a FastAPI backend. Completions go through LiteLLM with a
pool of API keys: when a key fails, the backend moves to the next key on its own.
LiteLLM caches responses, and each session's history is stored in SQLite.
Next to every assistant reply, the UI shows where the answer came from
(`LIVE_INFERENCE` or `LLM_CACHE`), the model, the latency, and the input and
output tokens for that request.

## 1. Live URLs
- Frontend: `<frontend-url>`
- Backend: `<backend-url>` (health: `<backend-url>/health`)

## 2. Run locally

### With Docker
```bash
cp .env.example .env        # put 2+ real keys in LLM_API_KEYS
make up                     # backend http://localhost:8000, frontend http://localhost:3000
make down
```
Without `make` (for example on Windows), run `docker compose up --build -d` and
`docker compose down`. If a port is taken, set `BACKEND_PORT` / `FRONTEND_PORT`
in `.env`. If you change the backend port, also update `VITE_API_BASE_URL`.

### Without Docker
```bash
# backend (Python 3.12+)
cd backend
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export LLM_API_KEYS=key-a,key-b ENABLE_FAILURE_SIMULATION=true DATABASE_URL=sqlite:///./app.db
uvicorn app.main:app --reload --port 8000
pytest -q                                            # offline, no real keys needed

# frontend (Node 20+)
cd frontend
npm install
npm run dev                                          # http://localhost:3000
```

### Environment variables
| Variable | Default | Meaning |
|---|---|---|
| `LLM_API_KEYS` | (required) | At least 2 comma-separated keys. Their ids are `key_1`, `key_2`, … in this order |
| `LLM_MODELS` | `gemini/gemini-2.5-flash` | LiteLLM model names. Key *N* uses model *N*, cycling through the list if there are fewer models than keys |
| `DATABASE_URL` | `sqlite:////data/app.db` | SQLite file location |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS origins: scheme included, no trailing slash |
| `ENABLE_FAILURE_SIMULATION` | `false` | `true` turns on the `X-Simulate-Failure` header |
| `CACHE_ENABLED` / `CACHE_TTL_SECONDS` | `true` / `86400` | LiteLLM in-memory cache |
| `DEFAULT_SYSTEM_PROMPT` | `You are a helpful assistant.` | |
| `MAX_HISTORY_MESSAGES` | `20` | Number of recent messages sent to the model with each request |
| `LLM_TIMEOUT_SECONDS` | `30` | Timeout for each provider call |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend build argument: the backend URL |

## 3. Design decisions

### Key fallback
- The key pool comes from `LLM_API_KEYS`, in order. Each key's id is its
  position (`key_1`, `key_2`, …). Key material is never logged, returned or
  hashed. Only the type and status code of provider errors are logged, and
  LiteLLM's own loggers are silenced. This matters because Gemini puts the key
  in the request URL, so a raw error message could expose it.
- The backend loops over the keys itself and calls `litellm.completion` with
  `num_retries=0`. Writing the loop by hand gives exact `key_id` and
  `fallback_attempts` values for every request, and the attempt counter stays
  local to each request.
- A key counts as failed, and the next key is tried, on any of these:
  - 429 or quota errors
  - 5xx errors
  - timeouts and connection errors
  - 401/403 errors (that key is invalid or revoked)
  - a 200 response with empty text

  If every key fails, the response is `503 {"detail": "all providers unavailable"}`.
- `X-Simulate-Failure` raises a `SimulatedFailure` with the chosen status code
  *before* any HTTP call, so demos use no quota. The failover loop handles it
  exactly like a real failure. Malformed parts of the header are ignored and
  never cause a 500.
- Requests that carry a simulated failure skip the cache **read**. Otherwise, a
  message that was already cached would answer from the cache and hide the
  failover being tested. Their results are still written to the cache.
- A global exception handler turns anything unexpected into
  `500 {"detail": "internal error"}`. There are no stack traces and no HTML
  error pages.

### Caching
- This uses LiteLLM's built-in cache (`Cache(type="local")`, in memory).
  LiteLLM removed its disk backend, so `litellm` is pinned to `1.77.7`, a stable
  release whose cache-hit path works.
- The cache key is the model plus the full message list sent to the LLM (system
  prompt, history and new message). LiteLLM's default hashing already does this,
  and the API key is not part of it. `build_messages` is deterministic, and
  messages are trimmed during validation, so the same question with trailing
  spaces gives the same key.
- `LLM_CACHE` vs `LIVE_INFERENCE` comes from LiteLLM's
  `_hidden_params["cache_hit"]` flag. A hit returns the stored reply and the
  token usage stored with it, with `key_id: null` and `fallback_attempts: 0`.
  It skips the network, so it is much faster than a live call.
- Before trying any key, the backend checks the cache under every model in the
  pool. Because the model is part of the cache key, a reply cached under key_2's
  model would otherwise be found only after key_1's provider call had failed.
  This way, a hit never waits on a failing provider.
- A cache hit is still a real turn, so it is written to the session history.

### SQLite session storage
- The `messages` table is exactly as specified. Two additions:
  - an index on `(session_id, id)`
  - a small `sessions` table that stores each session's system prompt
- The schema is created on startup. WAL mode is on, and each operation opens a
  short-lived connection, which is safe under FastAPI's threadpool.
- A user message and its assistant reply are inserted together in **one
  transaction**, and only after the LLM call succeeds. A 422 or 503 writes
  nothing.
- The server owns the history: the client sends only the new message. The most
  recent `MAX_HISTORY_MESSAGES` are sent to the model, which limits prompt
  growth. `GET /sessions/{id}/messages` returns the full history, oldest first,
  with no system row.
- System prompt rule: use the prompt from this request if there is one, else the
  prompt saved for the session, else `DEFAULT_SYSTEM_PROMPT`.
- In Docker, the database file is at `/data/app.db` on the named volume
  `appdata`, so history survives container restarts.

## 4. Verification
Set `B=<backend-url>` (or `localhost:8000`) and `H='content-type: application/json'`.

**Failover**
```bash
curl -s -X POST $B/chat -H "$H" -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"f-1","message":"ping"}' | jq '.metadata.key_id, .metadata.fallback_attempts'
# "key_2"  1
curl -s -X POST $B/chat -H "$H" -H 'X-Simulate-Failure: key_1=500' \
  -d '{"session_id":"f-1","message":"pong"}' | jq .metadata.key_id
# "key_2"
curl -s -w '\n%{http_code}\n' -X POST $B/chat -H "$H" -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"f-1","message":"again"}'
# {"detail":"all providers unavailable"} 503 (and f-1 history still has only 4 messages)
```

**Cache hit**
```bash
curl -s -X POST $B/chat -H "$H" -d '{"session_id":"c-1","message":"What is 2+2?"}' \
  | jq '{s:.metadata.resolution_source, l:.metadata.latency_ms, r:.reply}'
curl -s -X POST $B/chat -H "$H" -d '{"session_id":"c-2","message":"What is 2+2?"}' \
  | jq '{s:.metadata.resolution_source, l:.metadata.latency_ms, r:.reply, k:.metadata.key_id}'
# 2nd: LLM_CACHE, identical reply, far lower latency_ms, key_id null
```

**Multi-turn and per-request tokens**
```bash
curl -s -X POST $B/chat -H "$H" -d '{"session_id":"m-1","message":"My name is Sid."}' | jq .metadata
curl -s -X POST $B/chat -H "$H" -d '{"session_id":"m-1","message":"What is my name?"}' | jq '.reply, .metadata.input_tokens'
curl -s $B/sessions/m-1/messages | jq
# The reply knows the name. input_tokens grows with history but counts this request only.
```

**In the UI:** each assistant bubble shows the source, model, latency, input
tokens and output tokens. Under *Session settings*, the failover dropdown sends
`X-Simulate-Failure` so you can see `key_2 (after 1 failed)` or the readable 503
error in the chat.

**Tests:** `cd backend && pytest -q` runs 75 offline tests: health, the full 422
table, failover, the simulation header, cache labels and latency, sessions and
the response contract. The provider is replaced by LiteLLM's `mock_response`, so
the real LiteLLM cache is exercised without network access or keys.

## 5. Setup Used
- Editor: VS Code
- AI tools: Claude Code (Claude Opus 5.5)

## 6. Bonus features
- **Chat history sidebar** (ChatGPT style). Page load still starts a new session,
  as required. Past chats are listed by Today / Yesterday / Previous 7 days /
  Older, and clicking one reopens it with its messages and metadata so the
  conversation can continue. The list (ids and titles) is kept in the browser's
  `localStorage`; the messages come from the existing
  `GET /sessions/{id}/messages`, so no endpoint was added.
- **Markdown replies with a typing effect.** Headings, tables, lists, links and
  code are rendered, with HTML sanitised. New replies are typed out in at most
  1.5 s; click the bubble to show the whole reply.
- **Failover demo control in the UI.** A dropdown sends `X-Simulate-Failure`, so
  failover can be shown without curl.
- **Key and fallback count shown in each bubble**, next to the required metadata.
- **System prompt saved per session** in SQLite.
- **Empty replies count as a key failure**, so a 200 with blank text never
  reaches the user.
- **Cap on history sent to the model**, which limits prompt size and cost.
- **`/health` checks the database** and returns `503 {"detail":"database unavailable"}`
  if it can't reach it.
- **Docker hardening:** the backend runs as a non-root user and the compose file
  has a healthcheck. The backend honours `$PORT` for Render/Railway.
- **Client-side guards:** Send is disabled for empty input, input over 4000
  characters, and while a request is in flight. 422 errors are shown as
  readable text, never `[object Object]`.
