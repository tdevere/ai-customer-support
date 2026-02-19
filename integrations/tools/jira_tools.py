"""
Jira integration tools for tech support agent.
"""

from typing import Dict, Any, List
import httpx
from langchain_core.tools import tool
from shared.config import settings


@tool
async def create_jira_ticket(
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
    if not settings.jira_api_token or not settings.jira_base_url:
        return {"error": "Jira not configured"}

    url = f"{settings.jira_base_url}/rest/api/3/issue"
    headers = {
        "Authorization": f"Bearer {settings.jira_api_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "fields": {
            "project": {"key": "SUP"},  # Support project
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

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, json=payload, headers=headers, timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return {
                "key": data.get("key"),
                "id": data.get("id"),
                "url": f"{settings.jira_base_url}/browse/{data.get('key')}",
            }
        except httpx.HTTPError as e:
            return {"error": str(e)}


@tool
async def search_jira_tickets(
    query: str, max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    Search for existing Jira tickets.

    Args:
        query: JQL query string
        max_results: Maximum number of results to return

    Returns:
        List of matching tickets
    """
    if not settings.jira_api_token or not settings.jira_base_url:
        return [{"error": "Jira not configured"}]

    url = f"{settings.jira_base_url}/rest/api/3/search"
    headers = {
        "Authorization": f"Bearer {settings.jira_api_token}",
        "Content-Type": "application/json",
    }

    params = {
        "jql": query,
        "maxResults": max_results,
        "fields": "key,summary,status,priority,created",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url, params=params, headers=headers, timeout=30.0
            )
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
        except httpx.HTTPError as e:
            return [{"error": str(e)}]


@tool
async def get_jira_ticket(ticket_key: str) -> Dict[str, Any]:
    """
    Get details of a specific Jira ticket.

    Args:
        ticket_key: Jira ticket key (e.g., SUP-123)

    Returns:
        Ticket details
    """
    if not settings.jira_api_token or not settings.jira_base_url:
        return {"error": "Jira not configured"}

    url = f"{settings.jira_base_url}/rest/api/3/issue/{ticket_key}"
    headers = {
        "Authorization": f"Bearer {settings.jira_api_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
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
        except httpx.HTTPError as e:
            return {"error": str(e)}


# Export all tools
jira_tools = [create_jira_ticket, search_jira_tickets, get_jira_ticket]
