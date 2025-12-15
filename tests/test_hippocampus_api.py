from fastapi.testclient import TestClient

from brain.hippocampus.app import create_app
from brain.hippocampus.config import AppSettings, AuthSettings, HippocampusSettings, Mem0Settings
from brain.hippocampus.mem0_adapter import InMemoryMem0Client, Mem0Adapter


TEST_API_KEY = "test-api-key"
TEST_AUTH_HEADER = "X-API-Key"


def build_test_client(require_auth: bool = False) -> TestClient:
    auth_settings = AuthSettings(enabled=require_auth, api_keys=[TEST_API_KEY] if require_auth else [])
    settings = HippocampusSettings(
        app=AppSettings(),
        auth=auth_settings,
        mem0=Mem0Settings(api_key=None, backend="inmemory", summary_max_length=200, query_limit=10),
    )
    app = create_app(settings)
    # Make sure we use the in-memory backend for predictability
    app.state.mem0_adapter = Mem0Adapter(client=InMemoryMem0Client())
    return TestClient(app)


def test_create_and_query_memory():
    client = build_test_client()

    payload = {"user_id": "bob", "text": "Met Alice for coffee", "metadata": {"location": "cafe"}}
    resp = client.post("/memories", json=payload)
    assert resp.status_code == 200, resp.text
    memory_id = resp.json()["memory"]["id"]
    assert memory_id

    query = client.get("/memories/bob", params={"query": "coffee"})
    assert query.status_code == 200
    data = query.json()
    assert data["memories"], "should return at least one memory"
    assert data["memories"][0]["metadata"]["location"] == "cafe"


def test_summarize_endpoint():
    client = build_test_client()
    resp = client.post("/summaries", json={"texts": ["one", "two"]})
    assert resp.status_code == 200
    assert resp.json()["summary"].startswith("one")


def test_delete_memory_endpoint():
    client = build_test_client()
    payload = {"user_id": "bob", "text": "Delete me"}
    creation = client.post("/memories", json=payload)
    memory_id = creation.json()["memory"]["id"]

    resp = client.delete(f"/memories/{memory_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp_missing = client.delete(f"/memories/{memory_id}")
    assert resp_missing.status_code == 404


def test_auth_required_rejects_missing_key():
    client = build_test_client(require_auth=True)
    resp = client.post('/memories', json={"user_id": "bob", "text": "Secret"})
    assert resp.status_code == 401


def test_auth_allows_valid_key():
    client = build_test_client(require_auth=True)
    payload = {"user_id": "bob", "text": "Allowed"}
    resp = client.post('/memories', json=payload, headers={TEST_AUTH_HEADER: TEST_API_KEY})
    assert resp.status_code == 200

