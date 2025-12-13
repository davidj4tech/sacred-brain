from __future__ import annotations

import json
from unittest import mock

from sacred_brain.llm_client import LLMClient, MemoryItem


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
