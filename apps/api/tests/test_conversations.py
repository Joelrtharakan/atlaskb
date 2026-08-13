"""Conversation continuity, listing, and deletion — the backend half of the
chat-history-loss fix. The frontend fix makes the URL the source of truth and
always re-hydrates from GET /conversations/{id}; these tests cover what that
hydration actually gets back."""

import time

from app.config import settings


def test_conversation_id_continues_the_same_thread(client, auth_headers, stub_llm):
    r1 = client.post("/chat", headers=auth_headers, json={"question": "hello?"})
    convo_id = r1.json()["conversation_id"]

    r2 = client.post(
        "/chat",
        headers=auth_headers,
        json={"question": "follow-up", "conversation_id": convo_id},
    )
    assert r2.json()["conversation_id"] == convo_id

    detail = client.get(f"/conversations/{convo_id}", headers=auth_headers).json()
    assert len(detail["messages"]) == 4  # 2 user + 2 assistant turns


def test_unknown_conversation_id_404s_not_silently_forks(client, auth_headers, stub_llm):
    r = client.post(
        "/chat",
        headers=auth_headers,
        json={"question": "hi", "conversation_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 404


def test_message_stores_full_response_for_rehydration(client, auth_headers, stub_llm):
    r = client.post("/chat", headers=auth_headers, json={"question": "hello?"})
    convo_id = r.json()["conversation_id"]

    detail = client.get(f"/conversations/{convo_id}", headers=auth_headers).json()
    assistant_msg = next(m for m in detail["messages"] if m["role"] == "assistant")
    assert assistant_msg["response"] is not None
    assert assistant_msg["response"]["answer"] == r.json()["answer"]
    assert assistant_msg["response"]["message_id"] == r.json()["message_id"]
    # The stored record reflects how this answer was originally produced, not
    # replay history — this was the first time it was asked, so not cached.
    assert assistant_msg["response"]["cached"] is False

    user_msg = next(m for m in detail["messages"] if m["role"] == "user")
    assert user_msg["response"] is None


def test_message_response_json_survives_a_cache_hit(client, auth_headers, stub_llm, monkeypatch):
    # Cache is off by default across the suite (tests/conftest.py); this is
    # the one behavior that specifically needs it on.
    monkeypatch.setattr(settings, "cache_enabled", True)
    # Two separate (empty-history) conversations with the identical first
    # question — the cache key includes a history digest, so a hit only
    # happens when history matches too, not merely the question text.
    r1 = client.post("/chat", headers=auth_headers, json={"question": "cache me please"})
    assert r1.json()["cached"] is False
    r2 = client.post("/chat", headers=auth_headers, json={"question": "cache me please"})
    assert r2.json()["cached"] is True

    for r in (r1, r2):
        detail = client.get(
            f"/conversations/{r.json()['conversation_id']}", headers=auth_headers
        ).json()
        assistant_msg = next(m for m in detail["messages"] if m["role"] == "assistant")
        # Reads as freshly-generated either way — a cache hit is a
        # transport-layer detail of one specific request, not a property of
        # the underlying answer that reopening the conversation should show.
        assert assistant_msg["response"]["cached"] is False


def test_list_conversations_orders_by_last_activity(client, auth_headers, stub_llm):
    r1 = client.post("/chat", headers=auth_headers, json={"question": "first thread"})
    convo_a = r1.json()["conversation_id"]
    r2 = client.post("/chat", headers=auth_headers, json={"question": "second thread"})
    convo_b = r2.json()["conversation_id"]

    time.sleep(1.05)  # created_at/message timestamps have second resolution
    client.post(
        "/chat",
        headers=auth_headers,
        json={"question": "bumping the first thread", "conversation_id": convo_a},
    )

    ids = [c["id"] for c in client.get("/conversations", headers=auth_headers).json()]
    assert ids.index(convo_a) < ids.index(convo_b)


def test_list_conversations_pagination(client, auth_headers, stub_llm):
    for i in range(3):
        client.post("/chat", headers=auth_headers, json={"question": f"q{i}"})

    page1 = client.get("/conversations?limit=2&offset=0", headers=auth_headers).json()
    page2 = client.get("/conversations?limit=2&offset=2", headers=auth_headers).json()
    assert len(page1) == 2
    assert len(page2) == 1
    assert {c["id"] for c in page1}.isdisjoint({c["id"] for c in page2})


def test_delete_conversation(client, auth_headers, stub_llm):
    r = client.post("/chat", headers=auth_headers, json={"question": "throwaway"})
    convo_id = r.json()["conversation_id"]

    d = client.delete(f"/conversations/{convo_id}", headers=auth_headers)
    assert d.status_code == 204

    assert client.get(f"/conversations/{convo_id}", headers=auth_headers).status_code == 404
    ids = [c["id"] for c in client.get("/conversations", headers=auth_headers).json()]
    assert convo_id not in ids


def test_delete_conversation_other_users_404s(client, make_user, stub_llm):
    owner = make_user()
    other = make_user()
    r = client.post("/chat", headers=owner.headers, json={"question": "mine"})
    convo_id = r.json()["conversation_id"]

    d = client.delete(f"/conversations/{convo_id}", headers=other.headers)
    assert d.status_code == 404
    # Not actually deleted — the owner can still see it.
    assert client.get(f"/conversations/{convo_id}", headers=owner.headers).status_code == 200


def test_conversation_list_is_workspace_scoped(client, make_user, grant_membership, stub_llm):
    owner = make_user()
    member = make_user()  # own separate workspace
    grant_membership(member.user_id, owner.workspace_id, "viewer")

    client.post("/chat", headers=owner.headers, json={"question": "in workspace A"})

    # Member's own workspace never sees owner's conversation.
    ids = [c["id"] for c in client.get("/conversations", headers=member.headers).json()]
    assert ids == []

    # Different user in the SAME workspace still only sees their own thread
    # (conversations.py scopes by workspace AND user_id).
    same_ws_headers = member.in_ws(owner.workspace_id)
    ids_in_ws = [c["id"] for c in client.get("/conversations", headers=same_ws_headers).json()]
    assert ids_in_ws == []
