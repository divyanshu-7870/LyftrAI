# Lyftr AI Full-Stack Assignment: LLM Chatbot with Key Failover and Response Caching

Production-grade full-stack LLM Chatbot engineered with FastAPI, LiteLLM gateway, SQLite storage, and a React SPA frontend. Featuring automatic key fallback across provider failures, server-side response caching with LiteLLM, per-request token accounting, session isolation, and test failure simulation via the `X-Simulate-Failure` header.

---

## 1. Live URLs
* **Frontend**: https://lyftr-ai-iota.vercel.app/
* **Backend**: https://lyftrai-p0mb.onrender.com
* **GitHub Repository**: https://github.com/divyanshu-7870/LyftrAI

---

## 2. Run locally: with Docker and without

### Environment Setup
Create your local `.env` from `.env.example`:
```bash
cp .env.example .env
```
Fill in your Google Gemini API keys in `.env`:
```env
LLM_API_KEYS=your_key_1,your_key_2
DATABASE_URL=sqlite:///./data/app.db
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
ENABLE_FAILURE_SIMULATION=true
LLM_MODEL=gemini/gemini-3.5-flash-lite
DEFAULT_SYSTEM_PROMPT=You are a helpful and concise AI assistant.
```

### Option A: Run with Docker (Recommended)
Ensure Docker and Docker Compose are installed, then run:
```bash
make up
```
This builds and starts:
* **Frontend**: `http://localhost:3000`
* **Backend**: `http://localhost:8000`
* Persistent SQLite database mounted at the named volume `sqlite_data:/data`.

To stop the containers:
```bash
make down
```

### Option B: Run without Docker

#### Backend
1. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r backend/requirements.txt
   ```
2. Start the FastAPI server:
   ```bash
   PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
   ```

#### Frontend
1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```
2. Start the Vite development server:
   ```bash
   npm run dev
   ```
   Open `http://localhost:3000` in your browser.

#### Running Backend Tests
Execute the automated test suite verifying all assignment behavior:
```bash
make test
# Or directly:
PYTHONPATH=. ./venv/bin/pytest backend/tests/test_api.py -v
```

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### Key Fallback Architecture
* **Order & Identification**: The key pool configured in `LLM_API_KEYS` is indexed as `key_1`, `key_2`, ... and evaluated sequentially.
* **Resilience**: The gateway intercepts provider exceptions (`RateLimitError`, `APIError`, `Timeout`, `ServiceUnavailableError`, `5xx`, and quota exhausted responses) and immediately fails over to the next configured key without crashing or surfacing internal exceptions to the client.
* **Accountability**: `fallback_attempts` tracks how many keys failed before obtaining a successful answer.
* **Clean 503**: If all configured keys fail, the backend responds with HTTP 503 `{"detail": "all providers unavailable"}` and crucially ensures **nothing** from that failed request is persisted to session history.

### Response Caching
* **Implementation**: Uses LiteLLM's built-in caching mechanism (`litellm.cache = Cache(type="local")`).
* **Cache Key**: Generated over the model name and the complete conversation list sent to the LLM (`system_prompt` + previous SQLite history + new `message`).
* **Exact Contract**: On a cache hit:
  * `resolution_source`: `LLM_CACHE`
  * `reply`: Identical to cached response
  * `key_id`: `null` (never exposes key strings)
  * `fallback_attempts`: `0`
  * `latency_ms`: Lower than live inference
  * `input_tokens` & `output_tokens`: Usage stored with the cached response
* Different queries or differing message histories produce cache misses (`LIVE_INFERENCE`).

### SQLite Session Storage
* **Simplicity & Portability**: Session history is stored exclusively in SQLite without external dependencies (no Redis, no Postgres).
* **Automatic Initialization**: Database schema (`messages` table with indexed `session_id`) initializes automatically on app startup.
* **Volume Persistence**: In Docker, the database path is configured via `DATABASE_URL=sqlite:////data/app.db` and mapped to a named Docker volume (`/data`), preserving conversation history across container restarts.
* **Strict History Contract**: The client sends only the new message. The backend reconstructs context from SQLite. Failed requests (422/503) are never written to SQLite. The history endpoint `GET /sessions/{session_id}/messages` returns messages oldest-first and never exposes the system prompt.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### 1. Verify Health Check
```bash
curl -s http://localhost:8000/health
```
Expected response:
```json
{"status":"ok","keys_configured":2,"cache_enabled":true}
```

### 2. Verify Live Inference then Cache Hit
**Step 1: First request in a new session (LIVE_INFERENCE)**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-cache-1", "message": "What is the capital of France?"}'
```
Response:
* `resolution_source`: `"LIVE_INFERENCE"`
* `key_id`: `"key_1"`
* `latency_ms`: e.g. `800-1500` ms

**Step 2: Identical first message in a second new session (LLM_CACHE)**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-cache-2", "message": "What is the capital of France?"}'
```
Response:
* `resolution_source`: `"LLM_CACHE"`
* `key_id`: `null`
* `fallback_attempts`: `0`
* `latency_ms`: significantly faster (< 100 ms)
* Identical reply and token counts.

### 3. Verify Key Failover with `X-Simulate-Failure`
**Simulate `key_1=429`:**
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id": "test-fail-1", "message": "Tell me a fun fact."}'
```
Response:
* HTTP 200
* `key_id`: `"key_2"`
* `fallback_attempts`: `1`

**Simulate all keys failing `*=429`:**
```bash
curl -s -i -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id": "test-fail-all", "message": "Will fail."}'
```
Response:
* HTTP 503
* Body: `{"detail": "all providers unavailable"}`
* SQLite check: `GET /sessions/test-fail-all/messages` returns HTTP 404 `{"detail": "session not found"}`.

### 4. Verify Per-Message Token Usage & Multi-Turn Retention
```bash
# Turn 1
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "alex-session", "message": "My name is Alex."}'

# Turn 2
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "alex-session", "message": "What is my name?"}'
```
* Turn 2 correctly answers "Alex".
* `input_tokens` on Turn 2 reflects the prompt tokens of that specific request (system + history + new message), never a running conversation total.

---

## 5. Setup Used: your editor and AI tools
* **Operating System**: Linux (Ubuntu 25.10)
* **Editor & Environment**: Antigravity Pair-Programming Agent & VSCode
* **AI Model & Gateway**: Google Gemini (`gemini/gemini-3.5-flash-lite`), LiteLLM 1.110.3
* **Testing Tooling**: Pytest, AnyIO, HTTPX

---

## 6. Bonus features (if any): what you added beyond the requirements and why
* **Optional System Prompt Support**: Implemented in both the backend API contract and the React UI (`data-testid="system-prompt-input"`), allowing users to steer conversational behavior per session.
* **Dark / Light Mode Responsive Theme**: Built into the React UI with clean semantic styles matching modern developer tooling.
* **Input Key Bindings**: Send on `Enter` (and newline on `Shift+Enter`), with real-time disabled send state and automatic scroll to the newest message.
