"""
Jira integration tools for tech support agent.

Authentication
--------------
Jira Cloud REST API v3 requires HTTP Basic authentication using
base64-encoded ``email:api_token``.  The Bearer scheme used by Jira
Server/Data Center does NOT work for Jira Cloud and returns 401.

Tools are synchronous so they can be dispatched via LangChain's
synchronous ``tool.invoke()`` call inside agent nodes.
"""

import base64
from typing import Dict, Any, List

import httpx
from langchain_core.tools import tool

from shared.config import settings


def _basic_auth_header() -> str:
    """Return a Basic auth header value for Jira Cloud REST API v3."""
    credentials = f"{settings.jira_email}:{settings.jira_api_token}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def _jira_headers() -> Dict[str, str]:
    return {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


@tool
def create_jira_ticket(
    summary: str, description: str, issue_type: str = "Bug", priority: str = "Medium"
) -> Dict[str, Any]:
    """
    Create a new Jira ticket for technical issues.

    Args:
        summary: Brief summary of the issue
        description: Detailed description
        issue_type: Type of issue (Bug, Task, Story)
        priority: Priority level (Low, Medium, High, Critical)

    Returns:
        Created ticket details including key and URL
    """
    if (
        not settings.jira_api_token
        or not settings.jira_base_url
        or not settings.jira_email
    ):
        return {
            "error": "Jira not configured (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN required)"
        }

    url = f"{settings.jira_base_url}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": settings.jira_project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            },
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }
    }

    try:
        response = httpx.post(url, json=payload, headers=_jira_headers(), timeout=30.0)
        response.raise_for_status()
        data = response.json()
        return {
            "key": data.get("key"),
            "id": data.get("id"),
            "url": f"{settings.jira_base_url}/browse/{data.get('key')}",
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except httpx.HTTPError as e:
        return {"error": str(e)}


@tool
def search_jira_tickets(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Search for existing Jira tickets by JQL query.

    Args:
        query: JQL query string (e.g. 'project=SUP AND status=Open')
        max_results: Maximum number of results to return

    Returns:
        List of matching tickets with key, summary, status, priority
    """
    if (
        not settings.jira_api_token
        or not settings.jira_base_url
        or not settings.jira_email
    ):
        return [{"error": "Jira not configured"}]

    url = f"{settings.jira_base_url}/rest/api/3/search"
    params = {
        "jql": query,
        "maxResults": max_results,
        "fields": "key,summary,status,priority,created",
    }

    try:
        response = httpx.get(url, params=params, headers=_jira_headers(), timeout=30.0)
        response.raise_for_status()
        data = response.json()
        return [
            {
                "key": issue.get("key"),
                "summary": issue["fields"].get("summary"),
                "status": issue["fields"]["status"].get("name"),
                "priority": (
                    issue["fields"]["priority"].get("name")
                    if issue["fields"].get("priority")
                    else None
                ),
                "created": issue["fields"].get("created"),
                "url": f"{settings.jira_base_url}/browse/{issue.get('key')}",
            }
            for issue in data.get("issues", [])
        ]
    except httpx.HTTPStatusError as e:
        return [{"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}]
    except httpx.HTTPError as e:
        return [{"error": str(e)}]


@tool
def get_jira_ticket(ticket_key: str) -> Dict[str, Any]:
    """
    Get details of a specific Jira ticket.

    Args:
        ticket_key: Jira ticket key (e.g., SUP-123)

    Returns:
        Ticket details
    """
    if (
        not settings.jira_api_token
        or not settings.jira_base_url
        or not settings.jira_email
    ):
        return {"error": "Jira not configured"}

    url = f"{settings.jira_base_url}/rest/api/3/issue/{ticket_key}"

    try:
        response = httpx.get(url, headers=_jira_headers(), timeout=30.0)
        response.raise_for_status()
        data = response.json()
        return {
            "key": data.get("key"),
            "summary": data["fields"].get("summary"),
            "description": data["fields"].get("description"),
            "status": data["fields"]["status"].get("name"),
            "priority": (
                data["fields"]["priority"].get("name")
                if data["fields"].get("priority")
                else None
            ),
            "assignee": (
                data["fields"]["assignee"].get("displayName")
                if data["fields"].get("assignee")
                else None
            ),
            "created": data["fields"].get("created"),
            "updated": data["fields"].get("updated"),
            "url": f"{settings.jira_base_url}/browse/{data.get('key')}",
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except httpx.HTTPError as e:
        return {"error": str(e)}


# Export all tools
jira_tools = [create_jira_ticket, search_jira_tickets, get_jira_ticket]
