from conftest import chat

REQUIRED = {
    "resolution_source",
    "model",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "key_id",
    "fallback_attempts",
}


def test_chat_response_contract(client):
    body = chat(client, "t", "hi").json()
    assert set(body) >= {"session_id", "reply", "metadata"}
    assert body["session_id"] == "t"
    assert isinstance(body["reply"], str) and body["reply"]
    meta = body["metadata"]
    assert REQUIRED <= set(meta)
    assert meta["resolution_source"] in {"LIVE_INFERENCE", "LLM_CACHE"}
    assert isinstance(meta["model"], str)
    for k in ("latency_ms", "input_tokens", "output_tokens", "fallback_attempts"):
        assert type(meta[k]) is int, k
    assert meta["key_id"] == "key_1"


def test_cache_hit_contract_has_null_key_id(client):
    chat(client, "a", "hi")
    meta = chat(client, "b", "hi").json()["metadata"]
    assert "key_id" in meta and meta["key_id"] is None


def test_health_contract(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert type(body["keys_configured"]) is int
    assert type(body["cache_enabled"]) is bool


def test_cors_allows_frontend_origin(client):
    r = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-simulate-failure",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
