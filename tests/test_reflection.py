from __future__ import annotations

from types import SimpleNamespace

from brain.hippocampus.reflection import reflection_pass


class DummyAdapter:
    def __init__(self, memories):
        self.memories = memories

    def query_memories(self, user_id: str, query: str, limit: int = 3):
        return self.memories[:limit]


def test_reflection_adds_relevant_thread():
    mems = [
        {"text": "We talked about docker compose plugin syntax before", "metadata": {"kind": "thread"}},
    ]
    adapter = DummyAdapter(mems)
    result = reflection_pass(adapter, user_id="u", user_message="Tell me about compose", assistant_reply="You can use docker compose.")
    assert "Sam:" in result
    assert "compose" in result.lower()


def test_reflection_skips_facts():
    mems = [
        {"text": "Server listens on port 54321", "metadata": {"kind": "fact"}},
    ]
    adapter = DummyAdapter(mems)
    result = reflection_pass(adapter, user_id="u", user_message="tell me about compose", assistant_reply="ok")
    assert result == ""


def test_reflection_skips_irrelevant():
    mems = [
        {"text": "Unrelated topic about gardening", "metadata": {"kind": "thread"}},
    ]
    adapter = DummyAdapter(mems)
    result = reflection_pass(adapter, user_id="u", user_message="compose plugins", assistant_reply="ok")
    assert result == ""


def test_reflection_skips_sensitive_without_context():
    mems = [
        {"text": "API token xyz", "metadata": {"kind": "thread", "sensitive": True}},
    ]
    adapter = DummyAdapter(mems)
    result = reflection_pass(adapter, user_id="u", user_message="compose plugins", assistant_reply="ok")
    assert result == ""
