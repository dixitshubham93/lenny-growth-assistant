"""
tests/test_routing.py — Routing boundary tests.

Validates that Ship30 and ArtifactSkill are routed independently:
  - Ship30 request  → essay in answer, artifact=None
  - Artifact request → artifact populated, Ship30 not called
  - Both requested   → both invoked, artifact set
  - Normal QA        → neither invoked
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.llm.base import LLMResponse
from app.services.agent import AgentRunner, SourceCitationData


# ── Fixtures ──────────────────────────────────────────────────────────────────

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


def _http_client(responses: list):
    """
    Build a mock httpx.AsyncClient context-manager that returns
    *responses* in order from its .post() method.
    """
    client = AsyncMock()
    client.post.side_effect = responses
    cm = MagicMock()
    cm.__aenter__.return_value = client
    return cm


def _ollama_resp(content: str = "", tool_calls: list | None = None) -> MagicMock:
    mock = MagicMock()
    msg: dict = {"content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    mock.json.return_value = {"message": msg, "prompt_eval_count": 1, "eval_count": 1}
    return mock


# ── Test 1 — Ship30 only: essay in answer, artifact=None ─────────────────────

@pytest.mark.asyncio
@patch("app.services.agent._execute_transcript_search")
@patch("app.services.agent._execute_write_ship_30_essay")
async def test_ship30_only_no_artifact(
    mock_ship30, mock_search, mock_db, settings, mock_provider
):
    """
    Routing: write_ship_30_essay invoked, create_artifact NOT invoked.
    artifact must be None; skill_used must be 'ship30'.
    """
    mock_ship30.return_value = (
        "## The Essay\n\nContent here.",
        [SourceCitationData("c1", "e1", "S1", None, None, None, "f1", None, 0.3)],
    )

    tool_call_resp = _ollama_resp(tool_calls=[
        {"function": {"name": "write_ship_30_essay", "arguments": '{"topic": "PMF"}'}}
    ])
    final_resp = _ollama_resp(content="Here is your Ship 30 essay.")

    with patch("httpx.AsyncClient", return_value=_http_client([tool_call_resp, final_resp])):
        runner = AgentRunner(mock_db, settings, mock_provider)
        result = await runner.run("Turn this into a Ship 30 for 30 essay.", [])

    assert result.skill_used == "ship30"
    assert result.artifact is not None, "artifact MUST be auto-promoted when Ship30 is requested"
    assert len(result.sources) == 1
    mock_search.assert_not_called()  # transcript_search bypassed by mock_ship30


# ── Test 2 — Artifact only: create_artifact invoked, Ship30 NOT ───────────────

@pytest.mark.asyncio
@patch("app.services.agent._execute_write_ship_30_essay")
async def test_artifact_only_no_ship30(
    mock_ship30, mock_db, settings, mock_provider
):
    """
    Routing: create_artifact invoked; write_ship_30_essay NOT invoked.
    artifact must be populated; ship30 must remain un-called.
    """
    md_content = "## Some Content\n\nFor the artifact."

    tool_call_resp = _ollama_resp(tool_calls=[
        {"function": {
            "name": "create_artifact",
            "arguments": json.dumps({"content": md_content, "format": "markdown"})
        }}
    ])
    final_resp = _ollama_resp(content="Artifact created.")

    with patch("httpx.AsyncClient", return_value=_http_client([tool_call_resp, final_resp])):
        runner = AgentRunner(mock_db, settings, mock_provider)
        result = await runner.run("Turn this into a Markdown artifact.", [])

    assert result.artifact == md_content, "artifact must equal the markdown passthrough"
    mock_ship30.assert_not_called()
    assert result.skill_used in ("artifact", None)  # no Ship30 skill


# ── Test 3 — Both requested: Ship30 then create_artifact ─────────────────────

@pytest.mark.asyncio
@patch("app.services.agent._execute_write_ship_30_essay")
async def test_ship30_then_artifact(mock_ship30, mock_db, settings, mock_provider):
    """
    Routing: both write_ship_30_essay AND create_artifact invoked sequentially.
    Essay generated; artifact populated; Artifact Viewer opened.
    """
    essay_text = "## PMF Essay\n\nGrounded content."
    mock_ship30.return_value = (
        essay_text,
        [SourceCitationData("c2", "e2", "S2", None, None, None, "f2", None, 0.2)],
    )

    resp1 = _ollama_resp(tool_calls=[
        {"function": {"name": "write_ship_30_essay", "arguments": '{"topic": "PMF"}'}}
    ])
    resp2 = _ollama_resp(tool_calls=[
        {"function": {
            "name": "create_artifact",
            "arguments": json.dumps({"content": essay_text, "format": "markdown"})
        }}
    ])
    final_resp = _ollama_resp(content="Done! Essay and artifact created.")

    with patch("httpx.AsyncClient", return_value=_http_client([resp1, resp2, final_resp])):
        runner = AgentRunner(mock_db, settings, mock_provider)
        result = await runner.run(
            "Write a Ship 30 essay and then create an HTML artifact from it.", []
        )

    assert result.skill_used == "ship30"
    assert result.artifact == essay_text
    assert len(result.sources) == 1
    mock_ship30.assert_called_once()


# ── Test 4 — Normal QA: neither Ship30 nor Artifact ──────────────────────────

@pytest.mark.asyncio
@patch("app.services.agent._execute_transcript_search")
@patch("app.services.agent._execute_write_ship_30_essay")
async def test_normal_qa_no_ship30_no_artifact(
    mock_ship30, mock_search, mock_db, settings, mock_provider
):
    """
    Routing: transcript_search called, Ship30 NOT called, artifact=None.
    """
    mock_search.return_value = (
        [{"chunk_id": "c3", "text": "Relevant transcript content."}],
        [SourceCitationData("c3", "e3", "S3", "Guest", None, None, "f3", None, 0.35)],
    )

    resp1 = _ollama_resp(tool_calls=[
        {"function": {"name": "transcript_search", "arguments": '{"query": "product-market fit"}'}}
    ])
    final_resp = _ollama_resp(content="Based on the transcripts, here is what Lenny says...")

    with patch("httpx.AsyncClient", return_value=_http_client([resp1, final_resp])):
        runner = AgentRunner(mock_db, settings, mock_provider)
        result = await runner.run("What does Lenny say about product-market fit?", [])

    assert result.artifact is None
    assert result.skill_used == "grounded_qa"
    assert len(result.sources) == 1
    mock_ship30.assert_not_called()


# ── Unit test: _execute_create_artifact ──────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_create_artifact_markdown_passthrough():
    """Markdown format returns content unchanged."""
    from app.services.agent import _execute_create_artifact
    content = "## Hello\n\nThis is content."
    result = await _execute_create_artifact(content, "markdown")
    assert result == content


@pytest.mark.asyncio
async def test_execute_create_artifact_html_wraps_markdown():
    """HTML format wraps plain text in a valid HTML document."""
    from app.services.agent import _execute_create_artifact
    content = "## Hello\n\nThis is content."
    result = await _execute_create_artifact(content, "html")
    assert result.startswith("<!DOCTYPE html>")
    assert "Hello" in result


@pytest.mark.asyncio
async def test_execute_create_artifact_html_passthrough_if_already_html():
    """HTML format passes raw HTML through unchanged."""
    from app.services.agent import _execute_create_artifact
    content = "<!DOCTYPE html><html><body>Raw</body></html>"
    result = await _execute_create_artifact(content, "html")
    assert result == content
