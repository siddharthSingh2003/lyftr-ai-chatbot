"""Offline test harness. The provider is stubbed at `llm._provider_call` by
injecting LiteLLM's own `mock_response`, so the real LiteLLM cache is exercised
but no network or real key is ever used."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# app.main builds a module-level app at import; give it a valid environment.
os.environ.setdefault("LLM_API_KEYS", "test-secret-aaa,test-secret-bbb")
os.environ.setdefault("DATABASE_URL", "sqlite:///./.pytest-import.db")

import litellm  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import llm  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

KEYS = ["test-secret-aaa", "test-secret-bbb", "test-secret-ccc"]


class FakeProvider:
    """Records calls, can fail per key, replies deterministically."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.fail: dict[str, Exception] = {}  # api_key -> exception to raise
        self.reply_text: str | None = None
        self.delay = 0.05  # live calls are slower than cache hits

    def live_calls(self) -> int:
        return len([c for c in self.calls if c["api_key"] not in self.fail])

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["api_key"] in self.fail:
            raise self.fail[kwargs["api_key"]]
        last_user = kwargs["messages"][-1]["content"]
        text = self.reply_text if self.reply_text is not None else f"echo: {last_user}"
        return litellm.completion(**kwargs, mock_response=text, mock_delay=self.delay)


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        api_keys=KEYS[:2],
        models=["gemini/gemini-2.5-flash"],
        database_url=f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        allowed_origins=["http://localhost:3000"],
        enable_failure_simulation=True,
        cache_enabled=True,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def provider(monkeypatch) -> FakeProvider:
    fake = FakeProvider()
    monkeypatch.setattr(llm, "_provider_call", fake)
    return fake


@pytest.fixture
def make_client(tmp_path, provider):
    clients = []

    def _make(**overrides) -> TestClient:
        client = TestClient(create_app(make_settings(tmp_path, **overrides)))
        client.__enter__()  # runs lifespan: schema init + fresh LiteLLM cache
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)
    litellm.cache = None


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture
def db(client):
    return client.app.state.db


def chat(client, session_id: str, message: str, headers: dict | None = None, **extra):
    return client.post(
        "/chat", json={"session_id": session_id, "message": message, **extra}, headers=headers or {}
    )


def row_count(db) -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
