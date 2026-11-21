from conftest import chat


def sent_messages(provider) -> list[dict]:
    return provider.calls[-1]["messages"]


def test_history_is_sent_back_to_the_model(client, provider):
    chat(client, "m-1", "My name is Sid.")
    chat(client, "m-1", "What is my name?")
    msgs = sent_messages(provider)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[1]["content"] == "My name is Sid."
    assert msgs[-1]["content"] == "What is my name?"


def test_sessions_are_isolated(client, provider):
    chat(client, "m-1", "My name is Sid.")
    chat(client, "m-2", "What is my name?")
    msgs = sent_messages(provider)
    assert [m["role"] for m in msgs] == ["system", "user"]


def test_history_endpoint_shape(client):
    chat(client, "m-3", "first")
    chat(client, "m-3", "second")
    body = client.get("/sessions/m-3/messages").json()
    assert body["session_id"] == "m-3"
    msgs = body["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in msgs[::2]] == ["first", "second"]
    assert all("metadata" not in m for m in msgs[::2])
    assert all(m["metadata"]["resolution_source"] for m in msgs[1::2])
    assert all(m["role"] != "system" for m in msgs)


def test_history_cap_limits_prompt_not_endpoint(make_client, provider):
    client = make_client(max_history_messages=4)
    for i in range(5):
        chat(client, "cap", f"msg {i}")
    assert len(sent_messages(provider)) == 1 + 4 + 1  # system + capped history + new
    assert len(client.get("/sessions/cap/messages").json()["messages"]) == 10


def test_system_prompt_persists_for_session(client, provider):
    chat(client, "sp", "hi", system_prompt="You are a pirate.")
    chat(client, "sp", "again")
    assert sent_messages(provider)[0] == {"role": "system", "content": "You are a pirate."}
    chat(client, "sp", "now", system_prompt="You are a poet.")
    assert sent_messages(provider)[0]["content"] == "You are a poet."


def test_default_system_prompt(client, provider):
    chat(client, "dp", "hi", system_prompt="")
    assert sent_messages(provider)[0]["content"] == "You are a helpful assistant."


def test_history_survives_app_restart(make_client):
    c1 = make_client()
    chat(c1, "persist", "remember me")
    c2 = make_client()  # same DB file, fresh app
    assert len(c2.get("/sessions/persist/messages").json()["messages"]) == 2


def test_tokens_are_per_request(client):
    a = chat(client, "t-1", "abcde").json()["metadata"]
    b = chat(client, "t-2", "vwxyz").json()["metadata"]
    assert a["input_tokens"] == b["input_tokens"]
    later = chat(client, "t-1", "fghij").json()["metadata"]
    # not a running total of previous requests' tokens
    assert later["output_tokens"] == a["output_tokens"]
