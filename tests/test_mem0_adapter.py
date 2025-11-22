from brain.hippocampus.mem0_adapter import InMemoryMem0Client, Mem0Adapter, SQLiteMem0Client
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
