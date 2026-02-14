from __future__ import annotations

from unittest import mock

from sacred_brain.llm_client import LLMClient, MemoryItem, _strip_think, load_llm_client_from_env


def test_generate_reply_calls_llm():
    client = LLMClient(base_url="http://localhost:4000", model="test-model", enabled=True)
    mem = [MemoryItem(title="t", summary="s")]
    response = {
        "choices": [{"message": {"content": "hi"}}],
    }
    with mock.patch("httpx.post") as mpost:
        mpost.return_value.json.return_value = response
        mpost.return_value.raise_for_status.return_value = None
        reply = client.generate_reply("hello", mem, "sys")
    assert reply == "hi"
    assert mpost.call_args[0][0].endswith("/v1/chat/completions")


def test_generate_reply_disabled():
    client = LLMClient(enabled=False)
    reply = client.generate_reply("x", [], "sys")
    assert reply is None


def test_generate_reply_fallback_on_error():
    client = LLMClient(base_url="http://localhost:4000", model="test-model", enabled=True, retries=0)
    with mock.patch("httpx.post", side_effect=Exception("boom")):
        reply = client.generate_reply("x", [], "sys")
    assert reply is None


def test_strip_think_tags():
    text = "<think>reasoning</think>Final answer."
    assert _strip_think(text) == "Final answer."
    text2 = "<think>only reasoning"
    assert _strip_think(text2) == "only reasoning"


def test_model_map_env(monkeypatch):
    monkeypatch.setenv("SAM_LLM_BASE_URL", "https://llm.ryer.org/v1")
    monkeypatch.delenv("SAM_LLM_MODEL", raising=False)
    monkeypatch.setenv(
        "SAM_LLM_MODEL_MAP",
        '{"https://llm.ryer.org/v1": "/content/models/deepseek.gguf"}',
    )
    client = load_llm_client_from_env()
    assert client.model == "/content/models/deepseek.gguf"
