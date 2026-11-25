import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
import os
import uuid

@pytest.fixture(autouse=True)
async def setup_database():
    await init_db()

@pytest.mark.anyio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["keys_configured"] >= 2
        assert data["cache_enabled"] is True

@pytest.mark.anyio
async def test_chat_validation_errors():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Missing session_id
        res = await client.post("/chat", json={"message": "hello"})
        assert res.status_code == 422
        assert "detail" in res.json()

        # Empty session_id
        res = await client.post("/chat", json={"session_id": "   ", "message": "hello"})
        assert res.status_code == 422
        assert "detail" in res.json()

        # Missing message
        res = await client.post("/chat", json={"session_id": "s-1"})
        assert res.status_code == 422
        assert "detail" in res.json()

        # Empty message
        res = await client.post("/chat", json={"session_id": "s-1", "message": "   "})
        assert res.status_code == 422
        assert "detail" in res.json()

        # Message over 4000 characters
        res = await client.post("/chat", json={"session_id": "s-1", "message": "a" * 4001})
        assert res.status_code == 422
        assert "detail" in res.json()

        # Malformed JSON
        res = await client.post(
            "/chat",
            content="not a json",
            headers={"Content-Type": "application/json"}
        )
        assert res.status_code == 422
        assert "detail" in res.json()

@pytest.mark.anyio
async def test_sessions_unknown_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        non_existent = "non-existent-session-" + str(uuid.uuid4())
        res = await client.get(f"/sessions/{non_existent}/messages")
        assert res.status_code == 404
        assert res.json() == {"detail": "session not found"}

@pytest.mark.anyio
async def test_simulate_all_providers_unavailable_503():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        s_id = "s-fail-" + str(uuid.uuid4())
        res = await client.post(
            "/chat",
            json={"session_id": s_id, "message": "Will fail"},
            headers={"X-Simulate-Failure": "*=429"}
        )
        assert res.status_code == 503
        assert res.json() == {"detail": "all providers unavailable"}

        # Verify nothing was saved to history
        hist = await client.get(f"/sessions/{s_id}/messages")
        assert hist.status_code == 404
        assert hist.json() == {"detail": "session not found"}

@pytest.mark.anyio
async def test_live_inference_then_cache_hit():
    unique_msg = "What is the boiling point of pure water in Celsius at 1 atm? Answer only the number."
    s1 = "s-cache1-" + str(uuid.uuid4())
    s2 = "s-cache2-" + str(uuid.uuid4())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First request in session 1 -> LIVE_INFERENCE
        res1 = await client.post("/chat", json={"session_id": s1, "message": unique_msg})
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["metadata"]["resolution_source"] == "LIVE_INFERENCE"
        assert d1["metadata"]["key_id"] in ("key_1", "key_2")
        assert d1["metadata"]["input_tokens"] > 0
        assert d1["metadata"]["output_tokens"] > 0
        live_latency = d1["metadata"]["latency_ms"]

        # Equivalent eligible request in session 2 -> LLM_CACHE
        res2 = await client.post("/chat", json={"session_id": s2, "message": unique_msg})
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["metadata"]["resolution_source"] == "LLM_CACHE"
        assert d2["reply"] == d1["reply"]
        assert d2["metadata"]["key_id"] is None
        assert d2["metadata"]["fallback_attempts"] == 0
        assert d2["metadata"]["input_tokens"] == d1["metadata"]["input_tokens"]
        assert d2["metadata"]["output_tokens"] == d1["metadata"]["output_tokens"]
        assert d2["metadata"]["latency_ms"] < live_latency

        # Different prompt in session 3 -> NOT from cache (LIVE_INFERENCE)
        s3 = "s-cache3-" + str(uuid.uuid4())
        res3 = await client.post("/chat", json={"session_id": s3, "message": "What is the freezing point of water in Celsius?"})
        assert res3.status_code == 200
        d3 = res3.json()
        assert d3["metadata"]["resolution_source"] == "LIVE_INFERENCE"

@pytest.mark.anyio
async def test_multi_turn_history_and_isolation():
    s_alex = "s-alex-" + str(uuid.uuid4())
    s_bob = "s-bob-" + str(uuid.uuid4())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Session Alex: Turn 1
        r1 = await client.post("/chat", json={"session_id": s_alex, "message": "My name is Alex. Remember it."})
        assert r1.status_code == 200

        # Session Alex: Turn 2
        r2 = await client.post("/chat", json={"session_id": s_alex, "message": "What is my name? Answer with just the name."})
        assert r2.status_code == 200
        assert "Alex" in r2.json()["reply"]

        # Session Bob: Turn 1
        r3 = await client.post("/chat", json={"session_id": s_bob, "message": "What is my name?"})
        assert r3.status_code == 200
        # Bob does NOT know about Alex
        assert "Alex" not in r3.json()["reply"]

        # Verify history endpoint for Alex: oldest first, no system prompt
        hist_alex = await client.get(f"/sessions/{s_alex}/messages")
        assert hist_alex.status_code == 200
        alex_data = hist_alex.json()
        assert alex_data["session_id"] == s_alex
        assert len(alex_data["messages"]) == 4  # user, assistant, user, assistant
        assert alex_data["messages"][0]["role"] == "user"
        assert alex_data["messages"][0]["content"] == "My name is Alex. Remember it."
        assert alex_data["messages"][1]["role"] == "assistant"
        assert alex_data["messages"][1]["metadata"]["resolution_source"] in ("LIVE_INFERENCE", "LLM_CACHE")
        assert alex_data["messages"][2]["role"] == "user"
        assert alex_data["messages"][3]["role"] == "assistant"

@pytest.mark.anyio
async def test_failover_simulation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # key_1=429 -> key_2 succeeds with 200, fallback_attempts = 1
        s1 = "s-failover1-" + str(uuid.uuid4())
        res1 = await client.post(
            "/chat",
            json={"session_id": s1, "message": "Say hello from failover test 1"},
            headers={"X-Simulate-Failure": "key_1=429"}
        )
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["metadata"]["key_id"] == "key_2"
        assert d1["metadata"]["fallback_attempts"] == 1
        assert len(d1["reply"]) > 0

        # key_1=500 -> key_2 succeeds with 200, fallback_attempts = 1
        s2 = "s-failover2-" + str(uuid.uuid4())
        res2 = await client.post(
            "/chat",
            json={"session_id": s2, "message": "Say hello from failover test 2"},
            headers={"X-Simulate-Failure": "key_1=500"}
        )
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["metadata"]["key_id"] == "key_2"
        assert d2["metadata"]["fallback_attempts"] == 1
