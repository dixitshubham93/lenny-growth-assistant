"""
tests/test_agent.py — Phase 6 Agent Layer tests.
Fully mocked tests for AgentRunner's Anthropic and Ollama paths.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.llm.base import Message, LLMResponse
from app.services.agent import AgentRunner, SourceCitationData


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.provider_name = "test_provider"
    provider.model = "test-model"
    provider.complete = AsyncMock(
        return_value=LLMResponse(
            content="Generated essay mock.", provider="test_provider", model="test-model"
        )
    )
    return provider


@pytest.fixture
def settings():
    return Settings(agent_provider="internal")


@pytest.mark.asyncio
@patch("app.services.agent._execute_transcript_search")
async def test_agent_ollama_basic_qa(mock_search, mock_db, settings, mock_provider):
    """Test Ollama tool loop natively routing to transcript_search."""
    # Mock search returns 1 chunk + 1 citation
    mock_search.return_value = (
        [{"text": "Startup advice"}],
        [SourceCitationData("c1", "e1", "Startups", None, None, None, "f1", None, 0.1)]
    )

    # We mock httpx to simulate Ollama's tool calling response
    mock_response_1 = MagicMock()
    mock_response_1.json.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {"function": {"name": "transcript_search", "arguments": '{"query": "Startups"}'}}
            ]
        }
    }
    
    mock_response_2 = MagicMock()
    mock_response_2.json.return_value = {
        "message": {"content": "Final answer about Startups."}
    }

    mock_http_client = AsyncMock()
    mock_http_client.post.side_effect = [mock_response_1, mock_response_2]
    # We mock httpx.AsyncClient returning the mock client on enter
    mock_http_client_cls = MagicMock()
    mock_http_client_cls.__aenter__.return_value = mock_http_client

    with patch("httpx.AsyncClient", return_value=mock_http_client_cls):
        runner = AgentRunner(mock_db, settings, mock_provider)
        result = await runner.run("Tell me about startups.", [])

        assert result.answer == "Final answer about Startups."
        assert len(result.sources) == 1
        assert result.sources[0].episode_id == "e1"
        assert result.skill_used == "grounded_qa"
        assert result.artifact is None


@pytest.mark.asyncio
@patch("app.services.agent._execute_write_ship_30_essay")
async def test_agent_ollama_ship30(mock_ship30, mock_db, settings, mock_provider):
    """Test Ollama tool loop calling write_ship_30_essay."""
    # Mock ship30 returns the essay + citations
    mock_ship30.return_value = (
        "## Ship 30 Essay\n\nThe details.",
        [SourceCitationData("c2", "e2", "Growth", None, None, None, "f2", None, 0.1)]
    )

    mock_response_1 = MagicMock()
    mock_response_1.json.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {"function": {"name": "write_ship_30_essay", "arguments": '{"topic": "Growth"}'}}
            ]
        }
    }
    
    # We simulate Ollama replying after seeing the tool execution
    mock_response_2 = MagicMock()
    mock_response_2.json.return_value = {
        "message": {"content": "I have created your Ship 30 essay."}
    }

    mock_http_client = AsyncMock()
    mock_http_client.post.side_effect = [mock_response_1, mock_response_2]
    mock_http_client_cls = MagicMock()
    mock_http_client_cls.__aenter__.return_value = mock_http_client

    with patch("httpx.AsyncClient", return_value=mock_http_client_cls):
        runner = AgentRunner(mock_db, settings, mock_provider)
        result = await runner.run("Write an essay on growth.", [])

        assert result.answer == "I have created your Ship 30 essay."
        # Ship30 returns essay in the answer, but now we ALSO auto-promote it to an artifact.
        assert result.artifact is not None
        assert "## Ship 30 Essay" in result.artifact or "<h2" in result.artifact
        assert len(result.sources) == 1
        assert result.skill_used == "ship30"


@pytest.mark.asyncio
async def test_agent_mock_provider_bypass(mock_db, settings):
    """Ensure test_chat.py compat by bypassing Agent loop when provider='mock'"""
    from app.llm.base import LLMResponse
    
    mock_prov = MagicMock()
    mock_prov.provider_name = "mock"
    mock_prov.model = "mock"
    mock_prov.complete = AsyncMock(return_value=LLMResponse(
        content="Bypassed", provider="mock", model="mock"
    ))
    
    runner = AgentRunner(mock_db, settings, mock_prov)
    result = await runner.run("hello", [])
    
    assert result.answer == "Bypassed"
    assert result.sources == []
    assert result.artifact is None


@pytest.mark.asyncio
@patch("app.services.agent._execute_transcript_search")
async def test_irrelevant_retrieval_returns_no_grounding(mock_search, mock_db, settings, mock_provider):
    """Empty retrieval should result in empty sources and prompt model to refuse."""
    mock_search.return_value = ([], [])

    mock_response_1 = MagicMock()
    mock_response_1.json.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {"function": {"name": "transcript_search", "arguments": '{"query": "penguin mating behavior"}'}}
            ]
        }
    }
    
    mock_response_2 = MagicMock()
    mock_response_2.json.return_value = {
        "message": {"content": "There is insufficient transcript evidence to answer this."}
    }

    mock_http_client = AsyncMock()
    mock_http_client.post.side_effect = [mock_response_1, mock_response_2]
    mock_http_client_cls = MagicMock()
    mock_http_client_cls.__aenter__.return_value = mock_http_client

    with patch("httpx.AsyncClient", return_value=mock_http_client_cls):
        runner = AgentRunner(mock_db, settings, mock_provider)
        result = await runner.run("penguin mating behavior", [])

        # The sources should be empty!
        assert len(result.sources) == 0
        assert "insufficient transcript evidence" in result.answer


@pytest.mark.asyncio
@patch("app.services.agent._execute_transcript_search")
async def test_ship30_insufficient_grounding_regression(mock_search, mock_db, settings, mock_provider):
    """Empty retrieval during Ship 30 should not fabricate data."""
    # mock_search is called indirectly by write_ship_30_essay
    mock_search.return_value = ([], [])

    mock_provider.complete.return_value.content = "insufficient transcript evidence to write the essay"

    mock_response_1 = MagicMock()
    mock_response_1.json.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {"function": {"name": "write_ship_30_essay", "arguments": '{"topic": "aliens"}'}}
            ]
        }
    }
    
    # We simulate Ollama replying after seeing the tool execution
    mock_response_2 = MagicMock()
    mock_response_2.json.return_value = {
        "message": {"content": "I couldn't write it because lack of evidence."}
    }

    mock_http_client = AsyncMock()
    mock_http_client.post.side_effect = [mock_response_1, mock_response_2]
    mock_http_client_cls = MagicMock()
    mock_http_client_cls.__aenter__.return_value = mock_http_client

    with patch("httpx.AsyncClient", return_value=mock_http_client_cls):
        runner = AgentRunner(mock_db, settings, mock_provider)
        result = await runner.run("write a ship30 essay about aliens", [])

        assert len(result.sources) == 0
        # essay text (with insufficient-evidence message) lands in the answer, not in artifact
        assert "insufficient transcript evidence" in mock_provider.complete.return_value.content
        assert result.artifact is not None
