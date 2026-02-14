from unittest.mock import MagicMock

import pytest

from brain.hippocampus.bot_router import BotRouter
from brain.hippocampus.config import AgnoSettings, AppSettings, HippocampusSettings, SamLLMSettings
from brain.hippocampus.summarizers import SummarizerConfig


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.query_memories.return_value = []
    adapter.summarize_texts.return_value = "Adapter summary"
    return adapter


@pytest.fixture
def settings():
    return HippocampusSettings(
        app=AppSettings(),
        sam=SamLLMSettings(enabled=False),
        agno=AgnoSettings(enabled=False),
    )


@pytest.fixture
def summarizer_config():
    return SummarizerConfig(
        enabled=False,
        provider="litellm",
        model="gpt-4o",
        base_url=None,
        api_key=None
    )


def test_router_fallback_to_adapter_summarizer(settings, mock_adapter, summarizer_config):
    router = BotRouter(settings, mock_adapter, None, summarizer_config)
    reply = router.generate_response("alice", "hello", [], "room1")
    assert reply == "Adapter summary"
    mock_adapter.summarize_texts.assert_called_once()


def test_router_uses_sam_when_enabled(settings, mock_adapter, summarizer_config):
    settings.sam.enabled = True
    # We need to mock sam_generate_reply because it's imported in bot_router
    with MagicMock() as mock_sam_gen:
        from brain.hippocampus import bot_router
        orig = bot_router.sam_generate_reply
        bot_router.sam_generate_reply = MagicMock(return_value="Sam reply")

        router = BotRouter(settings, mock_adapter, None, summarizer_config)
        reply = router.generate_response("alice", "hello", [], "room1")

        assert reply == "Sam reply"
        bot_router.sam_generate_reply = orig


def test_router_uses_agno_when_enabled(settings, mock_adapter, summarizer_config):
    settings.agno.enabled = True
    mock_agno = MagicMock()
    mock_agno.run.return_value.content = "Agno reply"

    router = BotRouter(settings, mock_adapter, mock_agno, summarizer_config)
    reply = router.generate_response("alice", "hello", [], "room1")

    assert reply == "Agno reply"
    mock_agno.run.assert_called_once()
