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
