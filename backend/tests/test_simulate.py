import pytest

from app.simulate import parse_simulate_header
from conftest import chat, row_count

IDS = ["key_1", "key_2"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("key_1=429", {"key_1": 429}),
        ("key_1=429,key_2=500", {"key_1": 429, "key_2": 500}),
        (" key_1 = 502 , key_2=503 ", {"key_1": 502, "key_2": 503}),
        ("*=429", {"key_1": 429, "key_2": 429}),
        ("*=500,key_1=429", {"key_1": 429, "key_2": 500}),
        ("key_9=429", {}),
        ("key_1=418", {}),
        ("garbage", {}),
        ("key_1=", {}),
        ("=429", {}),
        ("key_1=abc", {}),
        ("", {}),
        (None, {}),
    ],
)
def test_parse(raw, expected):
    assert parse_simulate_header(raw, IDS, enabled=True) == expected


def test_disabled_ignores_header():
    assert parse_simulate_header("*=429", IDS, enabled=False) == {}


def test_key1_429_fails_over(client):
    r = chat(client, "s1", "ping", {"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["key_id"] == "key_2"
    assert meta["fallback_attempts"] == 1
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["reply"] == "echo: ping"  # a real answer, not an error string


def test_key1_500_fails_over(client):
    r = chat(client, "s2", "ping", {"X-Simulate-Failure": "key_1=500"})
    assert r.json()["metadata"]["key_id"] == "key_2"


def test_all_keys_simulated_is_503_nothing_written(client, db, provider):
    chat(client, "s3", "first")
    before = row_count(db)
    r = chat(client, "s3", "ping", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert row_count(db) == before
    assert len(client.get("/sessions/s3/messages").json()["messages"]) == 2


def test_simulated_failure_spends_no_quota(client, provider):
    chat(client, "s4", "ping", {"X-Simulate-Failure": "*=503"})
    assert provider.calls == []


def test_simulation_bypasses_cache_read(client):
    chat(client, "s5a", "same question")
    r = chat(client, "s5b", "same question", {"X-Simulate-Failure": "key_1=429"})
    meta = r.json()["metadata"]
    assert meta["key_id"] == "key_2"
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    r = chat(client, "s5c", "same question", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503


def test_header_ignored_when_flag_off(make_client):
    client = make_client(enable_failure_simulation=False)
    r = chat(client, "s6", "ping", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_1"


def test_malformed_header_never_500(client):
    for h in ("garbage", "key_1=", "=429", ",,,", "key_1=429=500"):
        assert chat(client, f"m-{h}", "ping", {"X-Simulate-Failure": h}).status_code == 200
