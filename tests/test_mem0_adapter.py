from brain.hippocampus.mem0_adapter import (
    InMemoryMem0Client,
    Mem0Adapter,
    SQLiteMem0Client,
    Mem0RemoteClient,
)
from brain.hippocampus.models import ExperienceCreate


def test_inmemory_add_and_query():
    adapter = Mem0Adapter(client=InMemoryMem0Client())
    exp = ExperienceCreate(user_id="alice", text="Met Bob at the park", metadata={"mood": "happy"})
    stored = adapter.add_experience(exp)

    assert stored.user_id == "alice"

    result = adapter.query_memories(user_id="alice", query="park")
    assert len(result) == 1
    assert result[0].metadata["mood"] == "happy"


def test_summary_falls_back_when_client_has_no_summarize():
    adapter = Mem0Adapter(client=InMemoryMem0Client(max_summary_chars=20))
    summary = adapter.summarize_texts(["one", "two", "three"])
    assert len(summary) <= 20
    assert summary.startswith("one")


def test_delete_memory_returns_true_when_removed():
    backend = InMemoryMem0Client()
    adapter = Mem0Adapter(client=backend)
    exp = ExperienceCreate(user_id="alice", text="Keep or delete?")
    stored = adapter.add_experience(exp)
    assert adapter.delete_memory(stored.id) is True
    assert adapter.query_memories("alice", "delete") == []


def test_sqlite_persists_between_clients(tmp_path):
    db_path = tmp_path / "memories.sqlite"
    client = SQLiteMem0Client(db_path=db_path)
    adapter = Mem0Adapter(client=client)
    exp = ExperienceCreate(user_id="alice", text="Met Bob at the park", metadata={"mood": "curious"})
    stored = adapter.add_experience(exp)
    client.close()

    new_client = SQLiteMem0Client(db_path=db_path)
    new_adapter = Mem0Adapter(client=new_client)
    results = new_adapter.query_memories("alice", "park")
    assert len(results) == 1
    assert results[0].id == stored.id
    assert results[0].metadata["mood"] == "curious"
    new_client.close()


def test_sqlite_delete_prunes_persisted_memory(tmp_path):
    db_path = tmp_path / "memories.sqlite"
    client = SQLiteMem0Client(db_path=db_path)
    adapter = Mem0Adapter(client=client)
    exp = ExperienceCreate(user_id="alice", text="Need to forget this detail")
    stored = adapter.add_experience(exp)

    assert adapter.delete_memory(stored.id) is True
    assert adapter.query_memories("alice", "detail") == []
    client.close()


class _StubRemoteClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._stored_id = "remote-1"

    def add_memory(self, user_id: str, text: str, metadata=None):
        self.calls.append("add")
        return {"id": self._stored_id, "user_id": user_id, "text": text, "metadata": metadata or {}}

    def query_memories(self, user_id: str, query: str, limit: int = 5):
        self.calls.append("query")
        return [
            {
                "id": self._stored_id,
                "user_id": user_id,
                "text": f"{query} summary",
                "metadata": {},
                "score": 0.9,
            }
        ]

    def delete_memory(self, memory_id: str):
        self.calls.append("delete")
        return {"deleted": memory_id == self._stored_id}

    def summarize(self, texts, max_length=None):
        self.calls.append("summarize")
        return "remote summary"


class _FailingRemoteClient:
    def add_memory(self, *args, **kwargs):
        raise RuntimeError("remote add failed")

    def query_memories(self, *args, **kwargs):
        raise RuntimeError("remote query failed")

    def delete_memory(self, *args, **kwargs):
        raise RuntimeError("remote delete failed")

    def summarize(self, *args, **kwargs):
        raise RuntimeError("remote summarize failed")


def test_remote_client_success_path():
    remote = _StubRemoteClient()
    adapter = Mem0Adapter(client=remote)
    exp = ExperienceCreate(user_id="alice", text="Remote memory")
    record = adapter.add_experience(exp)

    assert record.id == "remote-1"
    assert remote.calls[0] == "add"

    queried = adapter.query_memories("alice", "Remote")
    assert queried[0].id == "remote-1"
    assert adapter.fallback_client.query_memories("alice", "Remote") == []

    assert adapter.delete_memory("remote-1") is True
    assert adapter.summarize_texts(["one", "two"]) == "remote summary"


def test_remote_client_failure_falls_back_to_memory():
    remote = _FailingRemoteClient()
    adapter = Mem0Adapter(client=remote)
    exp = ExperienceCreate(user_id="alice", text="Fallback memory")
    record = adapter.add_experience(exp)

    fallback_results = adapter.query_memories("alice", "Fallback")
    assert fallback_results[0].id == record.id

    assert adapter.delete_memory(record.id) is True
    summary = adapter.summarize_texts(["offline"])
    assert summary.startswith("offline")


def test_mem0_remote_client_wraps_sdk(monkeypatch):
    calls = {}

    class _FakeMemoryClient:
        def __init__(self, api_key=None, host=None):
            calls["init"] = {"api_key": api_key, "host": host}

        def add(self, messages, user_id, metadata=None):
            calls["add"] = {"messages": messages, "user_id": user_id, "metadata": metadata}
            return {"results": [{"id": "sdk-1", "memory": "Remember me", "user_id": user_id}]}

        def search(self, query, user_id=None, top_k=None, limit=None):
            calls["search"] = {"query": query, "user_id": user_id, "top_k": top_k, "limit": limit}
            return {"results": [{"id": "sdk-1", "memory": "Remember me", "user_id": user_id, "score": 0.88}]}

        def delete(self, memory_id):
            calls["delete"] = {"memory_id": memory_id}
            return {"message": "Memory deleted successfully"}

    class _FakeModule:
        MemoryClient = _FakeMemoryClient

    def _fake_import(module_name):
        if module_name == "mem0":
            return _FakeModule()
        raise ModuleNotFoundError(module_name)

    monkeypatch.setattr("brain.hippocampus.mem0_adapter.import_module", _fake_import)

    client = Mem0RemoteClient(api_key="secret", backend_url="https://api.mem0.ai")
    record = client.add_memory(user_id="alice", text="Remember this", metadata={"topic": "test"})
    assert record["text"] == "Remember me"

    results = client.query_memories(user_id="alice", query="remember", limit=2)
    assert results[0]["text"] == "Remember me"

    deleted = client.delete_memory("sdk-1")
    assert deleted == {"deleted": True}

    assert calls["init"] == {"api_key": "secret", "host": "https://api.mem0.ai"}
    assert calls["add"]["messages"][0]["content"] == "Remember this"
    assert calls["search"]["top_k"] == 2
    assert calls["delete"]["memory_id"] == "sdk-1"
