import pytest

from conftest import chat, row_count


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"session_id": "s1"},
        {"message": "hi"},
        {"session_id": "s1", "message": "   \n\t "},
        {"session_id": "", "message": "hi"},
        {"session_id": "   ", "message": "hi"},
        {"session_id": "s1", "message": "a" * 4001},
        {"session_id": "s" * 129, "message": "hi"},
        {"session_id": 123, "message": "hi"},
        {"session_id": "s1", "message": None},
    ],
)
def test_invalid_bodies_are_422_and_write_nothing(client, db, provider, body):
    r = client.post("/chat", json=body)
    assert r.status_code == 422
    assert "detail" in r.json()
    assert provider.calls == []
    assert row_count(db) == 0


def test_malformed_json_is_422(client, db):
    r = client.post(
        "/chat", content='{"session_id":"s1","message":', headers={"content-type": "application/json"}
    )
    assert r.status_code == 422
    assert "detail" in r.json()
    assert row_count(db) == 0


def test_missing_content_type_is_422(client):
    r = client.post("/chat", content="session_id=s1&message=hi")
    assert r.status_code == 422
    assert "detail" in r.json()


def test_boundaries_accepted(client):
    assert chat(client, "s1", "a" * 4000).status_code == 200
    assert chat(client, "s" * 128, "hi").status_code == 200
    # 4000 chars once trimmed
    assert chat(client, "s2", "  " + "b" * 4000 + "\n").status_code == 200


def test_message_is_trimmed_before_storage(client):
    chat(client, "trim", "  hello  ")
    msgs = client.get("/sessions/trim/messages").json()["messages"]
    assert msgs[0]["content"] == "hello"


def test_unicode_roundtrip(client):
    text = "héllo 👋 مرحبا 你好"
    chat(client, "uni", text)
    assert client.get("/sessions/uni/messages").json()["messages"][0]["content"] == text


def test_session_id_is_opaque(client):
    for sid in ("../../etc/passwd", "a'; DROP TABLE messages;--"):
        assert chat(client, sid, "hi").status_code == 200
    assert client.get("/health").status_code == 200


def test_extra_fields_ignored(client):
    r = client.post("/chat", json={"session_id": "x", "message": "hi", "foo": 1})
    assert r.status_code == 200


def test_unknown_session_history_is_404(client):
    r = client.get("/sessions/does-not-exist/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}
