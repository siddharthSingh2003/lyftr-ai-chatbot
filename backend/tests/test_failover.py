import litellm

from conftest import KEYS, chat, row_count

M = "gemini/gemini-2.5-flash"


def rate_limited():
    return litellm.RateLimitError(message="quota", llm_provider="gemini", model=M)


def test_first_key_answers(client):
    meta = chat(client, "f0", "hello").json()["metadata"]
    assert meta["key_id"] == "key_1"
    assert meta["fallback_attempts"] == 0


def test_real_429_fails_over(client, provider):
    provider.fail[KEYS[0]] = rate_limited()
    r = chat(client, "f1", "hello")
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_2"
    assert r.json()["metadata"]["fallback_attempts"] == 1


def test_5xx_and_timeout_fail_over_across_three_keys(make_client, provider):
    client = make_client(api_keys=KEYS)
    provider.fail[KEYS[0]] = litellm.InternalServerError(message="x", llm_provider="gemini", model=M)
    provider.fail[KEYS[1]] = litellm.Timeout(message="x", llm_provider="gemini", model=M)
    meta = chat(client, "f2", "hello").json()["metadata"]
    assert meta["key_id"] == "key_3"
    assert meta["fallback_attempts"] == 2


def test_auth_error_on_one_key_fails_over(client, provider):
    provider.fail[KEYS[0]] = litellm.AuthenticationError(message="bad key", llm_provider="gemini", model=M)
    assert chat(client, "f3", "hello").json()["metadata"]["key_id"] == "key_2"


def test_empty_reply_counts_as_failure(client, provider):
    provider.reply_text = "   "
    r = chat(client, "f4", "hello")
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}


def test_all_keys_fail_is_503_and_writes_nothing(client, db, provider):
    provider.fail[KEYS[0]] = rate_limited()
    provider.fail[KEYS[1]] = litellm.ServiceUnavailableError(message="x", llm_provider="gemini", model=M)
    r = chat(client, "f5", "hello")
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert row_count(db) == 0
    assert client.get("/sessions/f5/messages").status_code == 404


def test_errors_never_leak_key_material(client, provider, caplog):
    provider.fail[KEYS[0]] = rate_limited()
    provider.fail[KEYS[1]] = rate_limited()
    r = chat(client, "f6", "hello")
    assert "test-secret" not in r.text
    assert "test-secret" not in caplog.text


def test_models_cycle_across_keys(make_client, provider):
    models = ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-flash-lite"]
    client = make_client(models=models)
    provider.fail[KEYS[0]] = rate_limited()
    meta = chat(client, "f7", "hello").json()["metadata"]
    assert [c["model"] for c in provider.calls] == models
    assert meta["model"] == models[1]
    assert meta["key_id"] == "key_2"


def test_unexpected_exception_is_json_500(client, monkeypatch):
    from app import main as main_module  # noqa: F401

    def boom(*_a, **_k):
        raise ValueError("kaboom with secret")

    monkeypatch.setattr(client.app.state.db, "get_messages", boom)
    c = client.__class__(client.app, raise_server_exceptions=False)
    r = c.post("/chat", json={"session_id": "e", "message": "hi"})
    assert r.status_code == 500
    assert r.json() == {"detail": "internal error"}
