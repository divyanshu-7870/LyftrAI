# REQUIREMENTS_CHECKLIST.md
# Lyftr AI Full-Stack Assignment: LLM Chatbot with Key Failover and Response Caching

Status Legend:
- [ ] NOT IMPLEMENTED
- [~] IN PROGRESS
- [x] VERIFIED (Verified with actual tests and real outputs)

---

## 1. System Architecture & Tech Stack
- [x] Backend: Python + FastAPI
- [x] Frontend: React (SPA)
- [x] Database: SQLite ONLY (no Redis, no Postgres, external services prohibited)
- [x] LLM Gateway: LiteLLM
- [x] Caching: LiteLLM built-in cache (in-memory or disk)
- [x] Containerization: Multi-stage Dockerfiles + `docker-compose.yml`
- [x] Local Orchestration: `Makefile` with `make up` and `make down`

---

## 2. Environment Variables & Security
- [x] `LLM_API_KEYS`: Comma-separated key pool, at least 2 keys (mapped to `key_1`, `key_2`, ...)
- [x] `DATABASE_URL`: SQLite location (e.g. `sqlite:////data/app.db`)
- [x] `ALLOWED_ORIGINS`: Comma-separated CORS origins
- [x] `ENABLE_FAILURE_SIMULATION`: `true` enables `X-Simulate-Failure` test hook
- [x] Secrets protection: NEVER hardcode or commit keys, secrets backend-only, `.env` gitignored, clean `.env.example` provided

---

## 3. SQLite Storage Layer
- [x] Schema created automatically on startup
- [x] Table `messages` matches schema:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `session_id TEXT NOT NULL`
  - `role TEXT NOT NULL` ('user' or 'assistant')
  - `content TEXT NOT NULL`
  - `metadata TEXT` (JSON string, assistant messages only)
  - `created_at TEXT NOT NULL` (ISO-8601 server time)
- [x] History stored per `session_id`
- [x] History persists across container/process restarts via Docker volume at `/data`
- [x] Failed requests (422 or 503) are NEVER added to session history

---

## 4. Exact API Contract

### GET /health
- [x] Exists at exact path `GET /health`
- [x] Returns HTTP 200 once app running, DB reachable, key pool loaded
- [x] Response JSON format:
  ```json
  { "status": "ok", "keys_configured": 2, "cache_enabled": true }
  ```

### POST /chat
- [x] Exists at exact path `POST /chat`
- [x] Request JSON format:
  - `session_id`: string, required, 1–128 chars, client-generated. Unknown ID starts new session.
  - `message`: string, required, 1–4000 chars after trimming whitespace.
  - `system_prompt`: string, optional; overrides default system prompt for this session.
- [x] Response 200 JSON format:
  ```json
  {
    "session_id": "s-7f3a",
    "reply": "The capital of France is Paris.",
    "metadata": {
      "resolution_source": "LIVE_INFERENCE",
      "model": "gemini/gemini-3.5-flash-lite",
      "latency_ms": 812,
      "input_tokens": 42,
      "output_tokens": 9,
      "key_id": "key_1",
      "fallback_attempts": 0
    }
  }
  ```
- [x] `resolution_source`: Exactly `LIVE_INFERENCE` or `LLM_CACHE`
- [x] `model`: LiteLLM model name that produced the reply
- [x] `latency_ms`: Server-measured round-trip time in milliseconds (integer)
- [x] `input_tokens`: Prompt tokens of this request (system + history + new message) as integer
- [x] `output_tokens`: Completion tokens of this reply as integer
- [x] `key_id`: String (`key_1`, `key_2`, ...) or `null` on `LLM_CACHE`. Never exposes real key string.
- [x] `fallback_attempts`: Count of keys that failed before success. `0` on `LLM_CACHE`.

### GET /sessions/{session_id}/messages
- [x] Exists at exact path `GET /sessions/{session_id}/messages`
- [x] Returns history from SQLite for `session_id`, oldest first
- [x] Does NOT include the system prompt
- [x] Response 200 format:
  ```json
  {
    "session_id": "s-7f3a",
    "messages": [
      { "role": "user", "content": "What is the capital of France?" },
      {
        "role": "assistant",
        "content": "The capital of France is Paris.",
        "metadata": { "resolution_source": "LIVE_INFERENCE", "input_tokens": 42, "output_tokens": 9 }
      }
    ]
  }
  ```

### Error Handling Contract
- [x] Missing or empty `message` / `session_id`, message > 4000 chars, malformed JSON → HTTP 422 with `{"detail": ...}`
- [x] Every key failed (rate-limited, quota exhausted or 5xx) → HTTP 503 with exact JSON: `{"detail": "all providers unavailable"}`
- [x] Unknown session in `GET /sessions/{session_id}/messages` → HTTP 404 with exact JSON: `{"detail": "session not found"}`
- [x] Never return Python stack traces or HTML error pages
- [x] Failed requests (422, 503) are NEVER inserted into session history

---

## 5. LiteLLM, Key Pool & Auto-Fallback
- [x] Configured with at least 2 keys (`key_1`, `key_2`, ...)
- [x] Automatic fallback on HTTP 429, quota errors, or 5xx errors to the next available key
- [x] Correct increment of `fallback_attempts` (e.g. 1 if `key_1` failed and `key_2` succeeded)
- [x] User never sees an unhandled backend exception or broken screen

---

## 6. X-Simulate-Failure Test Hook
- [x] Supported in `POST /chat` via `X-Simulate-Failure` header
- [x] Format: comma-separated `<key_id>=<status>` pairs (e.g. `key_1=429`, `key_1=429,key_2=500`, `*=429`)
- [x] Supported statuses: 429, 500, 502, 503
- [x] Active only when `ENABLE_FAILURE_SIMULATION=true` (must be true on deployed backend)
- [x] Effect: selected key behaves as if provider returned that status for that request only
- [x] `key_1=429` → 200 with `key_id = key_2`, `fallback_attempts = 1`
- [x] `key_1=500` → 200 with `key_id = key_2`, `fallback_attempts = 1`
- [x] `*=429` → 503 with `{"detail": "all providers unavailable"}` and nothing added to SQLite history
- [x] Simulated request returns real LLM answer when fallback succeeds, never fake error string in 200

---

## 7. Response Caching
- [x] Implemented using LiteLLM's built-in cache (in-memory or disk)
- [x] Cache key: model + full message list sent to LLM (system prompt + history + new message)
- [x] Identical first message in new session returns `LLM_CACHE` on second attempt
- [x] Different prompt never returned from cache
- [x] Cache hit behavior:
  - `resolution_source`: `LLM_CACHE`
  - `reply`: identical to original
  - `key_id`: `null`
  - `fallback_attempts`: `0`
  - `input_tokens` & `output_tokens`: match cached usage
  - `latency_ms`: faster than live call

---

## 8. Multi-Turn Session Behavior & Token Tracking
- [x] Backend stores history in SQLite per `session_id`; client sends only new message
- [x] Bot retains context across turns in the same session
- [x] No session leakage: Session A history does not bleed into Session B
- [x] Token tracking is per-request, NOT a running total
- [x] Tokens use real provider/LiteLLM usage metadata, never fabricated or estimated

---

## 9. Frontend Requirements & Contract
- [x] React SPA with clean, professional interface
- [x] Generate new session ID on each page load
- [x] Chat input clears after sending message
- [x] Backend errors (422, 503) displayed as readable chat messages, never blank screen/crash
- [x] Mandatory `data-testid` attributes:
  - [x] `data-testid="chat-input"` (text input / textarea for user message, empty after send)
  - [x] `data-testid="send-button"` (send button; Enter key also supported)
  - [x] `data-testid="assistant-message"` (container for each assistant reply)
  - [x] `data-testid="meta-source"` (inside assistant-message, exactly `LIVE_INFERENCE` or `LLM_CACHE`)
  - [x] `data-testid="meta-model"` (inside assistant-message, model name)
  - [x] `data-testid="meta-latency"` (inside assistant-message, e.g. `812 ms`)
  - [x] `data-testid="meta-input-tokens"` (inside assistant-message, integer)
  - [x] `data-testid="meta-output-tokens"` (inside assistant-message, integer)
  - [x] `data-testid="system-prompt-input"` (system-prompt field)
- [x] CORS configured so frontend origin is allowed by backend

---

## 10. Docker & Local Orchestration
- [x] Multi-stage Dockerfile for backend (lean runtime)
- [x] Multi-stage Dockerfile for frontend (lean runtime/static serving)
- [x] `docker-compose.yml` running backend at port 8000 and frontend at port 3000
- [x] Named volume mounted at `/data` for SQLite persistence
- [x] `Makefile` with working `make up` and `make down`
- [x] History survives container restart (verified with docker compose restart and make down / make up)

---

## 11. Backend Automated Tests
- [x] Unit & integration tests for all 3 endpoints
- [x] Tests for validation errors (422), not found (404), all keys failed (503)
- [x] Tests for multi-turn retention and session isolation
- [x] Tests for `X-Simulate-Failure` header behavior
- [x] Tests for LiteLLM caching (`LIVE_INFERENCE` vs `LLM_CACHE`)
- [x] Comprehensive `TEST_RESULTS.md` documenting expected vs actual results

---

## 12. Deployment & Verification
- [ ] Backend deployed and publicly reachable (BLOCKED - awaiting Render credentials/push)
- [ ] Frontend deployed and publicly reachable (BLOCKED - awaiting Vercel credentials/push)
- [ ] Frontend connected to live backend; CORS verified
- [ ] Public verification of health, live inference, caching, failover, token tracking, history

---

## 13. Documentation & Submission
- [x] Repository structure strictly matches:
  ```
  /backend
  /frontend
  docker-compose.yml
  Makefile
  .env.example
  README.md
  ```
- [x] `README.md` with exact required 6 sections:
  1. Live URLs
  2. Run locally: with Docker and without
  3. Design decisions: key fallback, caching, SQLite session storage
  4. Verification: how to see failover, cache hits and per-message token usage
  5. Setup Used: your editor and AI tools
  6. Bonus features (if any): what you added beyond the requirements and why
- [ ] 2–3 minute demo video script and checklist prepared
- [ ] `FINAL_AUDIT.md` verifying all evaluation criteria prior to submission
