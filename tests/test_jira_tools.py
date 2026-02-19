"""
Unit tests for Jira integration tools.

All HTTP calls are mocked — no real Jira instance required.
"""

import base64
import json
import pytest
from unittest.mock import MagicMock, patch

from shared.config import settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def jira_settings(monkeypatch):
    """Ensure settings have Jira credentials for all tests in this module."""
    monkeypatch.setattr(settings, "jira_email", "mock@example.com")
    monkeypatch.setattr(settings, "jira_api_token", "mock-jira-token")
    monkeypatch.setattr(settings, "jira_base_url", "https://mock.atlassian.net")
    monkeypatch.setattr(settings, "jira_project_key", "SUP")


def _make_httpx_response(json_body: dict, status_code: int = 200):
    """Build a minimal mock httpx response."""
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.status_code = status_code
    mock.text = json.dumps(json_body)
    mock.raise_for_status.return_value = None
    return mock


# ---------------------------------------------------------------------------
# create_jira_ticket
# ---------------------------------------------------------------------------


def test_create_jira_ticket_success(mocker):
    """create_jira_ticket returns key and URL on a 201 response."""
    from integrations.tools.jira_tools import create_jira_ticket

    mock_resp = _make_httpx_response({"key": "SUP-42", "id": "10042"}, 201)
    mock_post = mocker.patch(
        "integrations.tools.jira_tools.httpx.post", return_value=mock_resp
    )

    result = create_jira_ticket.invoke(
        {
            "summary": "App crashes on login",
            "description": "Reproducible 100% of the time on iOS 17.",
        }
    )

    assert result["key"] == "SUP-42"
    assert "SUP-42" in result["url"]
    assert result["id"] == "10042"
    mock_post.assert_called_once()

    # Verify Basic auth header is used (not Bearer)
    call_args = mock_post.call_args
    headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
    assert headers["Authorization"].startswith(
        "Basic "
    ), "Must use Basic auth, not Bearer"


def test_create_jira_ticket_basic_auth_encoding():
    """Basic auth header must be base64(email:token)."""
    from integrations.tools.jira_tools import _basic_auth_header

    header = _basic_auth_header()
    assert header.startswith("Basic ")
    encoded_part = header[len("Basic ") :]
    decoded = base64.b64decode(encoded_part).decode()
    assert decoded == "mock@example.com:mock-jira-token"


def test_create_jira_ticket_uses_configured_project_key(mocker):
    """create_jira_ticket sends the configurable project key, not a hardcoded value."""
    from integrations.tools.jira_tools import create_jira_ticket

    mock_resp = _make_httpx_response({"key": "OPS-7", "id": "20007"})
    mock_post = mocker.patch(
        "integrations.tools.jira_tools.httpx.post", return_value=mock_resp
    )

    create_jira_ticket.invoke(
        {"summary": "Test ticket", "description": "desc", "issue_type": "Task"}
    )

    call_args = mock_post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["fields"]["project"]["key"] == "SUP"


def test_create_jira_ticket_missing_config(monkeypatch):
    """Returns error dict when Jira credentials are not configured."""
    from integrations.tools.jira_tools import create_jira_ticket

    monkeypatch.setattr(settings, "jira_email", "")

    result = create_jira_ticket.invoke({"summary": "Test", "description": "Test desc"})
    assert "error" in result


# ---------------------------------------------------------------------------
# search_jira_tickets
# ---------------------------------------------------------------------------


def test_search_jira_tickets_success(mocker):
    """search_jira_tickets returns a list of matching tickets."""
    from integrations.tools.jira_tools import search_jira_tickets

    jira_response = {
        "issues": [
            {
                "key": "SUP-10",
                "fields": {
                    "summary": "Login failure",
                    "status": {"name": "Open"},
                    "priority": {"name": "High"},
                    "created": "2025-01-15T10:00:00.000+0000",
                },
            }
        ]
    }
    mock_resp = _make_httpx_response(jira_response)
    mocker.patch("integrations.tools.jira_tools.httpx.get", return_value=mock_resp)

    results = search_jira_tickets.invoke({"query": "project=SUP AND status=Open"})

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["key"] == "SUP-10"
    assert results[0]["status"] == "Open"
    assert results[0]["priority"] == "High"


def test_search_jira_tickets_missing_config(monkeypatch):
    """Returns error list when Jira is not configured."""
    from integrations.tools.jira_tools import search_jira_tickets

    monkeypatch.setattr(settings, "jira_api_token", "")

    results = search_jira_tickets.invoke({"query": "project=SUP"})
    assert isinstance(results, list)
    assert "error" in results[0]


# ---------------------------------------------------------------------------
# get_jira_ticket
# ---------------------------------------------------------------------------


def test_get_jira_ticket_success(mocker):
    """get_jira_ticket returns full ticket details."""
    from integrations.tools.jira_tools import get_jira_ticket

    ticket_response = {
        "key": "SUP-42",
        "fields": {
            "summary": "App crashes on login",
            "description": {"content": []},
            "status": {"name": "In Progress"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Jane Dev"},
            "created": "2025-01-15T10:00:00.000+0000",
            "updated": "2025-01-16T12:00:00.000+0000",
        },
    }
    mock_resp = _make_httpx_response(ticket_response)
    mocker.patch("integrations.tools.jira_tools.httpx.get", return_value=mock_resp)

    result = get_jira_ticket.invoke({"ticket_key": "SUP-42"})

    assert result["key"] == "SUP-42"
    assert result["summary"] == "App crashes on login"
    assert result["status"] == "In Progress"
    assert result["assignee"] == "Jane Dev"
    assert "SUP-42" in result["url"]


# ---------------------------------------------------------------------------
# HTTP error paths
# ---------------------------------------------------------------------------


def _http_status_error(status_code: int = 404, body: str = "Not Found"):
    """Build a minimal httpx.HTTPStatusError."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = body
    return httpx.HTTPStatusError(
        f"{status_code} {body}",
        request=MagicMock(),
        response=mock_response,
    )


def _http_error(msg: str = "connection error"):
    import httpx

    return httpx.HTTPError(msg)


def test_create_jira_ticket_http_status_error(mocker):
    """create_jira_ticket returns error dict on HTTPStatusError (e.g. 400)."""
    from integrations.tools.jira_tools import create_jira_ticket

    mocker.patch(
        "integrations.tools.jira_tools.httpx.post",
        side_effect=_http_status_error(400, "Bad Request"),
    )
    result = create_jira_ticket.invoke({"summary": "fail", "description": "fail"})
    assert "error" in result
    assert "400" in result["error"]


def test_create_jira_ticket_http_error(mocker):
    """create_jira_ticket returns error dict on network HTTPError."""
    from integrations.tools.jira_tools import create_jira_ticket

    mocker.patch(
        "integrations.tools.jira_tools.httpx.post",
        side_effect=_http_error("timeout"),
    )
    result = create_jira_ticket.invoke({"summary": "fail", "description": "fail"})
    assert "error" in result


def test_search_jira_tickets_http_status_error(mocker):
    """search_jira_tickets returns error list on HTTPStatusError."""
    from integrations.tools.jira_tools import search_jira_tickets

    mocker.patch(
        "integrations.tools.jira_tools.httpx.get",
        side_effect=_http_status_error(403, "Forbidden"),
    )
    result = search_jira_tickets.invoke({"query": "project=SUP"})
    assert isinstance(result, list)
    assert "error" in result[0]
    assert "403" in result[0]["error"]


def test_search_jira_tickets_http_error(mocker):
    """search_jira_tickets returns error list on network error."""
    from integrations.tools.jira_tools import search_jira_tickets

    mocker.patch(
        "integrations.tools.jira_tools.httpx.get",
        side_effect=_http_error("dns failure"),
    )
    result = search_jira_tickets.invoke({"query": "project=SUP"})
    assert isinstance(result, list)
    assert "error" in result[0]


def test_get_jira_ticket_http_status_error(mocker):
    """get_jira_ticket returns error dict on HTTPStatusError."""
    from integrations.tools.jira_tools import get_jira_ticket

    mocker.patch(
        "integrations.tools.jira_tools.httpx.get",
        side_effect=_http_status_error(404, "Not Found"),
    )
    result = get_jira_ticket.invoke({"ticket_key": "SUP-MISSING"})
    assert "error" in result
    assert "404" in result["error"]


def test_get_jira_ticket_http_error(mocker):
    """get_jira_ticket returns error dict on network error."""
    from integrations.tools.jira_tools import get_jira_ticket

    mocker.patch(
        "integrations.tools.jira_tools.httpx.get",
        side_effect=_http_error("connection refused"),
    )
    result = get_jira_ticket.invoke({"ticket_key": "SUP-OFFLINE"})
    assert "error" in result


def test_get_jira_ticket_missing_config(monkeypatch):
    """Returns error dict when Jira credentials are not configured."""
    from integrations.tools.jira_tools import get_jira_ticket

    monkeypatch.setattr(settings, "jira_base_url", "")

    result = get_jira_ticket.invoke({"ticket_key": "SUP-1"})
    assert "error" in result
