import os

import pytest

from app.config import load_settings


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_health_reports_cache_disabled(make_client):
    r = make_client(cache_enabled=False).get("/health")
    assert r.json()["cache_enabled"] is False


def test_health_never_leaks_keys(client):
    assert "test-secret" not in client.get("/health").text


def test_health_db_missing_is_json_503(client, db):
    os.remove(db.path)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(db.path + suffix):
            os.remove(db.path + suffix)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"detail": "database unavailable"}


def test_settings_require_two_keys(monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", "only-one")
    with pytest.raises(RuntimeError, match="at least 2"):
        load_settings()
    monkeypatch.delenv("LLM_API_KEYS")
    with pytest.raises(RuntimeError):
        load_settings()


def test_settings_parse(monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", " a , b ,c")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://x.app/, http://localhost:3000")
    monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "TRUE")
    s = load_settings()
    assert s.api_keys == ["a", "b", "c"]
    assert s.key_ids == ["key_1", "key_2", "key_3"]
    assert s.allowed_origins == ["https://x.app", "http://localhost:3000"]
    assert s.enable_failure_simulation is True


def test_db_directory_is_created(make_client, tmp_path):
    nested = tmp_path / "a" / "b" / "app.db"
    c = make_client(database_url=f"sqlite:///{nested.as_posix()}")
    assert c.get("/health").status_code == 200
    assert nested.exists()


def test_unknown_route_is_json(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert "detail" in r.json()
