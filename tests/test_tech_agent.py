"""
Unit tests for the tech support specialist agent.

Creates a fresh agent with mocked LLM and mocked Jira HTTP calls for each test.
"""

import json
import pytest
from unittest.mock import MagicMock

from shared.config import settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def jira_settings(monkeypatch):
    monkeypatch.setattr(settings, "jira_email", "mock@example.com")
    monkeypatch.setattr(settings, "jira_api_token", "mock-jira-token")
    monkeypatch.setattr(settings, "jira_base_url", "https://mock.atlassian.net")
    monkeypatch.setattr(settings, "jira_project_key", "SUP")


def _base_state(**overrides) -> dict:
    state = {
        "messages": [],
        "user_id": "user_abc",
        "query": "The app crashes when I upload a file larger than 10 MB.",
        "response": "",
        "confidence": 0.0,
        "sources": [],
        "tool_results": [],
        "jira_ticket": {},
    }
    state.update(overrides)
    return state


def _make_llm_pair(
    mocker, *, tool_calls=None, final_text="Here is the fix.\nCONFIDENCE: 0.80"
):
    mock_llm_with_tools = MagicMock()
    tool_response = MagicMock()
    tool_response.content = ""
    tool_response.tool_calls = tool_calls or []
    mock_llm_with_tools.invoke.return_value = tool_response

    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools
    final_response = MagicMock()
    final_response.content = final_text
    mock_llm.invoke.return_value = final_response

    mocker.patch("agents.tech_agent.AzureChatOpenAI", return_value=mock_llm)
    mocker.patch("agents.tech_agent.rag.retrieve_context", return_value=[])
    mocker.patch("agents.tech_agent.rag.format_context_for_prompt", return_value="")

    return mock_llm, mock_llm_with_tools


def _mock_httpx_post(mocker, json_body: dict):
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_body
    mock_resp.raise_for_status.return_value = None
    mocker.patch("integrations.tools.jira_tools.httpx.post", return_value=mock_resp)


def _mock_httpx_get(mocker, json_body: dict):
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_body
    mock_resp.raise_for_status.return_value = None
    mocker.patch("integrations.tools.jira_tools.httpx.get", return_value=mock_resp)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_tech_agent_no_tool_calls(mocker):
    """Agent returns a response with no Jira tool calls needed."""
    _make_llm_pair(mocker, final_text="Try clearing your cache.\nCONFIDENCE: 0.78")

    from agents.tech_agent import create_tech_agent

    agent = create_tech_agent()
    result = agent.invoke(_base_state())

    assert result["response"] == "Try clearing your cache."
    assert result["confidence"] == pytest.approx(0.78)
    assert result["tool_results"] == []


def test_tech_agent_creates_jira_ticket(mocker):
    """Agent dispatches create_jira_ticket when LLM requests it."""
    _make_llm_pair(
        mocker,
        tool_calls=[
            {
                "name": "create_jira_ticket",
                "args": {
                    "summary": "File upload crash > 10MB",
                    "description": "Reproducible on iOS and Android",
                    "issue_type": "Bug",
                    "priority": "High",
                },
            }
        ],
        final_text="I've created ticket SUP-99 for the engineering team.\nCONFIDENCE: 0.88",
    )
    _mock_httpx_post(mocker, {"key": "SUP-99", "id": "30099"})

    from agents.tech_agent import create_tech_agent

    agent = create_tech_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    tr = result["tool_results"][0]
    assert tr["tool"] == "create_jira_ticket"
    assert tr["result"]["key"] == "SUP-99"


def test_tech_agent_searches_existing_tickets(mocker):
    """Agent dispatches search_jira_tickets and returns matching ticket list."""
    _make_llm_pair(
        mocker,
        tool_calls=[
            {
                "name": "search_jira_tickets",
                "args": {"query": "project=SUP AND text~'upload'"},
            }
        ],
        final_text="Found 1 existing ticket.\nCONFIDENCE: 0.82",
    )
    _mock_httpx_get(
        mocker,
        {
            "issues": [
                {
                    "key": "SUP-55",
                    "fields": {
                        "summary": "Upload fails on large files",
                        "status": {"name": "Open"},
                        "priority": {"name": "Medium"},
                        "created": "2025-12-01T00:00:00.000+0000",
                    },
                }
            ]
        },
    )

    from agents.tech_agent import create_tech_agent

    agent = create_tech_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    assert result["tool_results"][0]["result"][0]["key"] == "SUP-55"


def test_tech_agent_unknown_tool_error(mocker):
    """Unknown tool calls are recorded as errors without raising exceptions."""
    _make_llm_pair(
        mocker,
        tool_calls=[{"name": "hack_the_planet", "args": {}}],
        final_text="Sorry, I can't do that.\nCONFIDENCE: 0.10",
    )

    from agents.tech_agent import create_tech_agent

    agent = create_tech_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    assert "Unknown tool" in result["tool_results"][0]["result"]["error"]


def test_tech_tool_invoke_raises_error_stored(mocker):
    """When a known tool's invoke() raises, the exception is captured in tool_results."""
    mock_tool = mocker.MagicMock()
    mock_tool.name = "search_jira_tickets"
    mock_tool.invoke.side_effect = Exception("Jira connection refused")
    mocker.patch("agents.tech_agent.jira_tools", [mock_tool])

    _make_llm_pair(
        mocker,
        tool_calls=[{"name": "search_jira_tickets", "args": {"query": "crash"}}],
        final_text="Could not search tickets.\nCONFIDENCE: 0.30",
    )

    from agents.tech_agent import create_tech_agent

    agent = create_tech_agent()
    result = agent.invoke(_base_state())

    assert len(result["tool_results"]) == 1
    assert "error" in result["tool_results"][0]["result"]
    assert "Jira connection refused" in result["tool_results"][0]["result"]["error"]


def test_tech_confidence_parse_failure_stays_default(mocker):
    """Non-numeric CONFIDENCE value falls back to 0.5 without crashing."""
    _make_llm_pair(mocker, final_text="Here is the fix.\nCONFIDENCE: uncertain")

    from agents.tech_agent import create_tech_agent

    agent = create_tech_agent()
    result = agent.invoke(_base_state())

    assert result["confidence"] == pytest.approx(0.5)
