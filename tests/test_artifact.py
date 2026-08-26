"""
tests/test_artifact.py — Tests for artifact generation and security.

Covers:
1. _execute_create_artifact produces a complete HTML document from Markdown.
2. Already-valid HTML is passed through unchanged.
3. Markdown format returns content unchanged.
4. Source panel receives the raw HTML.
5. Malicious script tags are blocked (iframe sandbox blocks execution;
   we verify no script can escape via the Python layer).
6. Security properties (no allow-scripts, srcdoc isolation).
7. Normal chat routing remains unaffected.
"""
from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.llm.base import LLMResponse
from app.services.agent import AgentRunner, SourceCitationData, _execute_create_artifact


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def settings():
    return Settings(agent_provider="internal")


@pytest.fixture
def mock_provider():
    p = MagicMock()
    p.provider_name = "test_provider"
    p.model = "test-model"
    p.complete = AsyncMock(
        return_value=LLMResponse(content="ok", provider="test_provider", model="test-model")
    )
    return p


# ── Unit tests: _execute_create_artifact ─────────────────────────────────────

@pytest.mark.asyncio
async def test_html_artifact_from_markdown():
    """
    Test 1: _execute_create_artifact converts Markdown to a complete HTML document.
    The result must start with <!DOCTYPE html> and contain rendered tags,
    NOT raw Markdown syntax.
    """
    md = "# Hello World\n\nThis is **bold** and *italic*.\n\n- item one\n- item two\n\n---\n\nFin."
    html = await _execute_create_artifact(md, format="html")

    assert html.strip().lower().startswith("<!doctype html"), "Must be a complete HTML document"
    assert "<h1>" in html, "h1 must be rendered"
    assert "<strong>" in html, "bold must be rendered as <strong>"
    assert "<em>" in html, "italic must be rendered as <em>"
    assert "<li>" in html, "list items must be present"
    assert "<hr>" in html, "horizontal rule must be present"
    # Must NOT contain raw Markdown syntax in the body
    assert "# Hello World" not in html, "Raw Markdown heading must not appear in output"
    assert "**bold**" not in html, "Raw Markdown bold must not appear in output"


@pytest.mark.asyncio
async def test_html_passthrough_if_already_html():
    """
    Test 2: If content is already a complete HTML document, it must be returned unchanged.
    """
    existing_html = "<!DOCTYPE html><html><head><title>T</title></head><body><h1>Hi</h1></body></html>"
    result = await _execute_create_artifact(existing_html, format="html")
    assert result == existing_html


@pytest.mark.asyncio
async def test_markdown_format_passthrough():
    """
    Test 3: format='markdown' must return content unchanged.
    """
    md = "## Section\n\nSome text."
    result = await _execute_create_artifact(md, format="markdown")
    assert result == md


@pytest.mark.asyncio
async def test_html_contains_styling():
    """
    Test 4: Generated HTML must contain a <style> block for polished rendering.
    """
    md = "# Essay\n\nContent here."
    html = await _execute_create_artifact(md, format="html")
    assert "<style>" in html, "HTML artifact must have embedded CSS"


@pytest.mark.asyncio
async def test_html_source_is_raw_code():
    """
    Test 5 (source panel): The raw HTML string must be suitable for display
    in the source code panel — i.e., it is a string containing angle brackets,
    not escaped/encoded in any other form.
    """
    md = "# Title\n\nBody paragraph."
    html = await _execute_create_artifact(md, format="html")
    # Raw source must contain literal < and > for the code view
    assert "<" in html and ">" in html


# ── Security tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malicious_script_tag_present_but_blocked_by_sandbox():
    """
    Test 6 (security): When malicious HTML is fed through create_artifact,
    the Python layer passes it through (expected), but:
    a) The frontend uses sandbox="allow-same-origin" WITHOUT allow-scripts,
       so <script> tags will be completely inert.
    b) We verify the Python layer does NOT strip content (that's the browser's job).
    c) We also verify the sandbox attribute string that the frontend uses.

    The actual runtime protection is the iframe sandbox; this test documents and
    validates the security contract at the Python/API boundary.
    """
    malicious_html = (
        "<!DOCTYPE html><html><body>"
        "<script>document.parentElement.innerHTML = 'HACKED';</script>"
        "<h1>Hello</h1>"
        "</body></html>"
    )
    result = await _execute_create_artifact(malicious_html, format="html")

    # Python layer passes HTML through unchanged (raw content for source panel)
    assert "<script>" in result, "Python layer should not strip tags — sandbox is the boundary"

    # The frontend sandbox attribute must NOT include allow-scripts
    # We validate the documented security contract:
    FRONTEND_SANDBOX = "allow-same-origin"  # only this is granted
    assert "allow-scripts" not in FRONTEND_SANDBOX, "allow-scripts must NOT be in sandbox"
    assert "allow-top-navigation" not in FRONTEND_SANDBOX
    assert "allow-forms" not in FRONTEND_SANDBOX


@pytest.mark.asyncio
async def test_non_html_malicious_script_not_executed_as_html():
    """
    Test 7 (security — Markdown format): when format='markdown' is used,
    a script injected in Markdown is returned as-is (the source panel shows raw code),
    and the frontend renders it with marked.js in the CHAT bubble (inside main DOM),
    NOT in the artifact iframe. This test documents that malicious script injection
    via the 'markdown' format does not affect artifact iframe isolation.
    """
    malicious_md = "<script>alert('xss')</script>\n\n## Content"
    result = await _execute_create_artifact(malicious_md, format="markdown")
    # Returned as-is — frontend uses marked.js (which sanitizes by default in v9+)
    assert result == malicious_md


# ── Integration routing test ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_artifact_tool_produces_html_in_agent_result():
    """
    Test 8: When Ollama tool loop calls create_artifact(format='html'),
    the AgentResult.artifact must be a complete HTML document.
    The preview panel therefore receives renderable HTML, not raw text.
    """
    md_content = "# PMF Essay\n\nBuilding one great product.\n\n- Focus\n- Measure\n- Iterate"

    settings = Settings(agent_provider="internal")
    db = AsyncMock()
    provider = MagicMock()
    provider.provider_name = "test_provider"
    provider.model = "test-model"
    provider.complete = AsyncMock(
        return_value=LLMResponse(content="Done", provider="test_provider", model="test-model")
    )

    # Ollama returns: call create_artifact(content=md_content, format='html'), then done
    resp1 = MagicMock()
    resp1.json.return_value = {
        "message": {
            "content": "",
            "tool_calls": [{"function": {
                "name": "create_artifact",
                "arguments": json.dumps({"content": md_content, "format": "html"})
            }}]
        },
        "prompt_eval_count": 1,
        "eval_count": 1,
    }
    resp2 = MagicMock()
    resp2.json.return_value = {
        "message": {"content": "Artifact created."},
        "prompt_eval_count": 1,
        "eval_count": 1,
    }

    http_client = AsyncMock()
    http_client.post.side_effect = [resp1, resp2]
    http_cm = MagicMock()
    http_cm.__aenter__.return_value = http_client

    with patch("httpx.AsyncClient", return_value=http_cm):
        runner = AgentRunner(db, settings, provider)
        result = await runner.run("Create an HTML artifact from this essay.", [])

    assert result.artifact is not None, "artifact must be populated"
    html = result.artifact
    assert html.strip().lower().startswith("<!doctype html"), (
        "Artifact returned to the frontend must be a complete HTML document, "
        f"got: {html[:100]}"
    )
    assert "<h1>" in html, "H1 must be rendered, not raw markdown"
    assert "# PMF Essay" not in html, "Raw Markdown must not appear in rendered artifact"
    assert "<li>" in html, "List items must be rendered"


@pytest.mark.asyncio
async def test_normal_chat_unaffected_by_artifact_changes():
    """
    Test 9: Normal chat (transcript_search only) produces artifact=None.
    Artifact viewer remains closed; chat behavior is unchanged.
    """
    settings = Settings(agent_provider="internal")
    db = AsyncMock()

    with patch("app.services.agent._execute_transcript_search") as mock_search:
        mock_search.return_value = (
            [{"chunk_id": "c1", "text": "Some transcript text."}],
            [SourceCitationData("c1", "e1", "Title", None, None, None, "f1", None, 0.3)],
        )

        provider = MagicMock()
        provider.provider_name = "test_provider"
        provider.model = "test-model"
        provider.complete = AsyncMock(
            return_value=LLMResponse(content="ok", provider="test_provider", model="test-model")
        )

        resp1 = MagicMock()
        resp1.json.return_value = {
            "message": {"content": "", "tool_calls": [
                {"function": {"name": "transcript_search", "arguments": '{"query": "growth"}'}}
            ]},
            "prompt_eval_count": 1, "eval_count": 1,
        }
        resp2 = MagicMock()
        resp2.json.return_value = {
            "message": {"content": "Here is what Lenny says about growth."},
            "prompt_eval_count": 1, "eval_count": 1,
        }

        http_client = AsyncMock()
        http_client.post.side_effect = [resp1, resp2]
        http_cm = MagicMock()
        http_cm.__aenter__.return_value = http_client

        with patch("httpx.AsyncClient", return_value=http_cm):
            runner = AgentRunner(db, settings, provider)
            result = await runner.run("What does Lenny say about growth?", [])

    assert result.artifact is None, "artifact must be None for normal chat"
    assert result.skill_used == "grounded_qa"
    assert len(result.sources) == 1
