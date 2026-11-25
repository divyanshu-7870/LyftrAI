# TEST_RESULTS.md
# Automated Backend Test Suite Verification

Suite: `backend/tests/test_api.py`
Framework: `pytest 9.2.0`, `anyio 4.16.0`, `httpx 0.28.1`
LLM Provider: Google Gemini
LiteLLM Model: `gemini/gemini-3.5-flash-lite`

| Test Name | Feature / Scenario | Expected Result | Actual Observed Result | Status |
|-----------|--------------------|-----------------|------------------------|--------|
| `test_health_endpoint` | `GET /health` contract | HTTP 200, `{"status": "ok", "keys_configured": >=2, "cache_enabled": true}` | HTTP 200, `{"status": "ok", "keys_configured": 2, "cache_enabled": true}` | **PASS** |
| `test_chat_validation_errors` | Input validation (missing/empty `session_id`, missing/empty `message`, >4000 chars, malformed JSON) | HTTP 422 with `{"detail": [...]}` | HTTP 422 with JSON detail for all validation failure cases | **PASS** |
| `test_sessions_unknown_404` | Non-existent `session_id` on `GET /sessions/{session_id}/messages` | HTTP 404, `{"detail": "session not found"}` | HTTP 404, `{"detail": "session not found"}` | **PASS** |
| `test_simulate_all_providers_unavailable_503` | `X-Simulate-Failure: *=429` | HTTP 503, `{"detail": "all providers unavailable"}`, nothing added to history | HTTP 503, `{"detail": "all providers unavailable"}`, history endpoint returns 404 | **PASS** |
| `test_live_inference_then_cache_hit` | Identical prompt across 2 sessions (cross-session first-message caching) + different prompt miss | Request 1: `LIVE_INFERENCE` with real tokens & latency. Request 2: `LLM_CACHE`, identical reply, `key_id: null`, `fallback_attempts: 0`, identical tokens, lower latency. Request 3: `LIVE_INFERENCE` | Request 1: `LIVE_INFERENCE`. Request 2: `LLM_CACHE`, identical reply, `key_id: null`, `fallback_attempts: 0`, lower latency (hit). Request 3: `LIVE_INFERENCE`. | **PASS** |
| `test_multi_turn_history_and_isolation` | Multi-turn retention (Alex) and session isolation (Bob) + SQLite history retrieval | Turn 2 remembers name "Alex". Bob does not know Alex. History endpoint returns oldest-first, no system prompt. | Turn 2 retained "Alex". Bob isolated. History endpoint returned 4 turns in order without system prompt. | **PASS** |
| `test_failover_simulation` | `X-Simulate-Failure: key_1=429` and `key_1=500` | HTTP 200, `key_id = "key_2"`, `fallback_attempts = 1`, real assistant reply | HTTP 200, `key_id = "key_2"`, `fallback_attempts = 1` for both 429 and 500 simulations. | **PASS** |

Summary: 7 tests run, 7 passed, 0 failed.

## Docker Container & SQLite Volume Persistence Verification

| Test Scenario | Steps Executed | Expected Result | Actual Observed Result | Status |
|---------------|----------------|-----------------|------------------------|--------|
| `make up` Clean Stack Startup | Built multi-stage Docker images and launched containers with compose | Both containers running (`backend:8000`, `frontend:3000`) | Both services healthy and responding | **PASS** |
| `GET /health` in Docker | HTTP GET to `http://localhost:8000/health` | HTTP 200, keys configured >= 2, cache enabled | HTTP 200, `{"status": "ok", "keys_configured": 2, "cache_enabled": true}` | **PASS** |
| Frontend HTTP 200 in Docker | HTTP GET to `http://localhost:3000` | Nginx serves compiled SPA with all assets | HTTP 200, Nginx 1.31.10 serving Vite SPA bundle | **PASS** |
| Real Containerized Chat Inference | POST to `/chat` with session `s-docker-alex` | HTTP 200, `LIVE_INFERENCE`, real tokens, real latency | HTTP 200, `LIVE_INFERENCE`, latency: 1470ms, input_tokens: 18, output_tokens: 19 | **PASS** |
| Multi-turn Context in Docker | Turn 2 query "What is my name?" | Retains earlier context, replies "Alex." | HTTP 200, reply: "Alex.", input_tokens: 49 | **PASS** |
| Session Isolation in Docker | Query "What is my name?" in new session `s-docker-bob` | Does not leak Alex context | HTTP 200, replies: "I don't know your name..." | **PASS** |
| Cross-Session Response Caching in Docker | Same initial prompt across `s-docker-cache1` and `s-docker-cache2` | Request 2 returns `LLM_CACHE`, identical reply, `key_id: null`, lower latency | Request 2: `LLM_CACHE`, identical reply "343", `key_id: null`, latency 251ms (< 696ms live) | **PASS** |
| `X-Simulate-Failure: key_1=429` in Docker | POST with failover header | Real answer via `key_2`, fallback_attempts: 1 | HTTP 200, `key_id: "key_2"`, `fallback_attempts: 1`, real answer returned | **PASS** |
| `X-Simulate-Failure: key_1=500` in Docker | POST with failover header | Real answer via `key_2`, fallback_attempts: 1 | HTTP 200, `key_id: "key_2"`, `fallback_attempts: 1`, real answer returned | **PASS** |
| `X-Simulate-Failure: *=429` in Docker | POST with all keys failed simulation | HTTP 503 `{"detail": "all providers unavailable"}`, nothing in SQLite history | HTTP 503 `{"detail": "all providers unavailable"}`, session history returns 404 | **PASS** |
| History Retrieval in Docker | GET `/sessions/s-docker-alex/messages` | Returns 4 turns in order without system prompt | HTTP 200, 4 turns returned in chronological order | **PASS** |
| SQLite Docker Volume Persistence Across Container Restart & `make down` / `make up` | Saved session `s-docker-persist-12345` with code `778899`, restarted container, then executed `make down` and `make up` | Previous session history survives and remains accessible | HTTP 200, 2 messages intact, code `778899` present | **PASS** |

## Public Post-Deployment Live Verification

Target Backend: `https://lyftrai-p0mb.onrender.com`
Target Frontend: `https://lyftr-ai-iota.vercel.app/`

| Public Test | Action / Request | Expected Result | Actual Observed Result | Status |
|-------------|------------------|-----------------|------------------------|--------|
| Public Frontend HTTP 200 | GET `https://lyftr-ai-iota.vercel.app/` | HTTP 200, assets served | HTTP 200, headers `access-control-allow-origin: *` | **PASS** |
| Public Backend Health | GET `https://lyftrai-p0mb.onrender.com/health` | HTTP 200, `{"status": "ok", "keys_configured": 2, "cache_enabled": true}` | HTTP 200, `{"status": "ok", "keys_configured": 2, "cache_enabled": true}` | **PASS** |
| Public Backend CORS | OPTIONS `https://lyftrai-p0mb.onrender.com/chat` with Origin `https://lyftr-ai-iota.vercel.app` | HTTP 200/204, allowed origin present | HTTP 200, `access-control-allow-origin: https://lyftr-ai-iota.vercel.app` | **PASS** |
| Public Live Inference (Turn 1) | POST `/chat` with session `s-public-eval-dbcb9bd7` | HTTP 200, `resolution_source: "LIVE_INFERENCE"`, `key_id: "key_1"`, real tokens | HTTP 200, `LIVE_INFERENCE`, `key_id: "key_1"`, latency: 748ms, input_tokens: 29, output_tokens: 23 | **PASS** |
| Public Multi-Turn Retention (Turn 2) | POST `/chat` query for name & code | Retains earlier context, returns "Alex" and code | HTTP 200, reply retains name and code, input_tokens: 65 | **PASS** |
| Public Cross-Session Caching | Same initial prompt across two separate public sessions | Request 2 returns `LLM_CACHE`, identical reply, `key_id: null`, latency < live call | Request 2: `LLM_CACHE`, identical reply, `key_id: null`, latency 1ms (< 564ms live) | **PASS** |
| Public `X-Simulate-Failure: key_1=429` | POST `/chat` with header | Falls back to `key_2` with real response | HTTP 200, `key_id: "key_2"`, `fallback_attempts: 1`, real answer returned | **PASS** |
| Public `X-Simulate-Failure: *=429` | POST `/chat` with all fail header | HTTP 503 `{"detail": "all providers unavailable"}` | HTTP 503 `{"detail": "all providers unavailable"}` | **PASS** |
| Public History Isolation for Failed Turns | GET `/sessions/s-pub-fail-all-.../messages` | HTTP 404 `{"detail": "session not found"}` | HTTP 404 `{"detail": "session not found"}` | **PASS** |
| Public Session History Endpoint | GET `/sessions/s-public-eval-dbcb9bd7/messages` | HTTP 200, 4 messages in order, no system prompt | HTTP 200, 4 turns returned in chronological order | **PASS** |
