from conftest import chat


def test_second_identical_first_message_is_cache_hit(client, provider):
    r1 = chat(client, "c-1", "What is 2+2?").json()
    r2 = chat(client, "c-2", "What is 2+2?").json()
    m1, m2 = r1["metadata"], r2["metadata"]

    assert m1["resolution_source"] == "LIVE_INFERENCE"
    assert m2["resolution_source"] == "LLM_CACHE"
    assert r2["reply"] == r1["reply"]
    assert m2["key_id"] is None
    assert m2["fallback_attempts"] == 0
    assert m2["model"] == m1["model"]
    # tokens are the usage stored with the cached response, not zeros
    assert m2["input_tokens"] == m1["input_tokens"] > 0
    assert m2["output_tokens"] == m1["output_tokens"] > 0
    assert m2["latency_ms"] < m1["latency_ms"]


def test_different_message_never_hits(client):
    chat(client, "d-1", "question one")
    meta = chat(client, "d-2", "question two").json()["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"


def test_different_system_prompt_misses(client):
    chat(client, "p-1", "hi", system_prompt="Be terse.")
    meta = chat(client, "p-2", "hi", system_prompt="Be verbose.").json()["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"


def test_same_message_later_in_session_misses(client):
    chat(client, "h-1", "repeat me")
    chat(client, "h-1", "something else")
    meta = chat(client, "h-1", "repeat me").json()["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"


def test_trailing_whitespace_same_key(client):
    chat(client, "w-1", "trim test")
    meta = chat(client, "w-2", "trim test   \n").json()["metadata"]
    assert meta["resolution_source"] == "LLM_CACHE"


def test_cache_hit_is_written_to_history(client):
    chat(client, "k-1", "cached turn")
    chat(client, "k-2", "cached turn")
    msgs = client.get("/sessions/k-2/messages").json()["messages"]
    assert len(msgs) == 2
    assert msgs[1]["metadata"]["resolution_source"] == "LLM_CACHE"


def test_cache_disabled_is_always_live(make_client):
    client = make_client(cache_enabled=False)
    chat(client, "x-1", "same")
    meta = chat(client, "x-2", "same").json()["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["key_id"] == "key_1"


def test_hit_cached_under_second_model_skips_failing_first_key(make_client, provider):
    import litellm

    from conftest import KEYS

    models = ["gemini/gemini-2.5-flash", "groq/openai/gpt-oss-120b"]
    client = make_client(models=models)
    provider.fail[KEYS[0]] = litellm.BadRequestError(message="no tier", llm_provider="gemini", model=models[0])
    first = chat(client, "mm-1", "cross model").json()["metadata"]
    assert first["key_id"] == "key_2" and first["model"] == models[1]

    calls_before = len(provider.calls)
    r = chat(client, "mm-2", "cross model").json()
    meta = r["metadata"]
    assert meta["resolution_source"] == "LLM_CACHE"
    assert meta["model"] == models[1]
    assert meta["key_id"] is None and meta["fallback_attempts"] == 0
    assert meta["input_tokens"] == first["input_tokens"] > 0
    assert len(provider.calls) == calls_before  # no provider touched, not even key_1
