"""
Shopify integration tools for returns agent.

All tools are synchronous so they can be dispatched via LangChain's
synchronous ``tool.invoke()`` call inside agent nodes.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

import httpx
from langchain_core.tools import tool

from shared.config import settings


def _shopify_headers() -> Dict[str, str]:
    return {
        "X-Shopify-Access-Token": settings.shopify_api_key,
        "Content-Type": "application/json",
    }


@tool
def get_order(order_id: str) -> Dict[str, Any]:
    """
    Retrieve order details from Shopify.

    Args:
        order_id: Shopify order ID

    Returns:
        Order details including items, shipping, and payment info
    """
    if not settings.shopify_api_key or not settings.shopify_shop_url:
        return {"error": "Shopify not configured"}

    url = f"{settings.shopify_shop_url}/admin/api/2024-01/orders/{order_id}.json"

    try:
        response = httpx.get(url, headers=_shopify_headers(), timeout=30.0)
        response.raise_for_status()
        order = response.json().get("order", {})
        return {
            "id": order.get("id"),
            "order_number": order.get("order_number"),
            "created_at": order.get("created_at"),
            "total_price": order.get("total_price"),
            "currency": order.get("currency"),
            "financial_status": order.get("financial_status"),
            "fulfillment_status": order.get("fulfillment_status"),
            "line_items": [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "quantity": item.get("quantity"),
                    "price": item.get("price"),
                }
                for item in order.get("line_items", [])
            ],
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except httpx.HTTPError as e:
        return {"error": str(e)}


@tool
def search_orders(customer_email: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search orders by customer email.

    Args:
        customer_email: Customer email address
        limit: Maximum number of orders to return

    Returns:
        List of orders
    """
    if not settings.shopify_api_key or not settings.shopify_shop_url:
        return [{"error": "Shopify not configured"}]

    url = f"{settings.shopify_shop_url}/admin/api/2024-01/orders.json"
    params = {"email": customer_email, "limit": limit, "status": "any"}

    try:
        response = httpx.get(
            url, headers=_shopify_headers(), params=params, timeout=30.0
        )
        response.raise_for_status()
        return [
            {
                "id": order.get("id"),
                "order_number": order.get("order_number"),
                "created_at": order.get("created_at"),
                "total_price": order.get("total_price"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
            }
            for order in response.json().get("orders", [])
        ]
    except httpx.HTTPStatusError as e:
        return [{"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}]
    except httpx.HTTPError as e:
        return [{"error": str(e)}]


@tool
def create_refund(
    order_id: str, amount: float, reason: str = "customer_request"
) -> Dict[str, Any]:
    """
    Create a refund for an order.

    Args:
        order_id: Shopify order ID
        amount: Refund amount
        reason: Refund reason

    Returns:
        Refund confirmation
    """
    if not settings.shopify_api_key or not settings.shopify_shop_url:
        return {"error": "Shopify not configured"}

    url = (
        f"{settings.shopify_shop_url}/admin/api/2024-01/orders/{order_id}/refunds.json"
    )
    payload = {
        "refund": {
            "note": reason,
            "notify": True,
            "transactions": [{"kind": "refund", "amount": str(amount)}],
        }
    }

    try:
        response = httpx.post(
            url, json=payload, headers=_shopify_headers(), timeout=30.0
        )
        response.raise_for_status()
        refund = response.json().get("refund", {})
        return {
            "id": refund.get("id"),
            "order_id": refund.get("order_id"),
            "created_at": refund.get("created_at"),
            "note": refund.get("note"),
            "transactions": refund.get("transactions", []),
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except httpx.HTTPError as e:
        return {"error": str(e)}


@tool
def check_return_eligibility(order_id: str) -> Dict[str, Any]:
    """
    Check if an order is eligible for return based on the 30-day return policy.

    Args:
        order_id: Shopify order ID

    Returns:
        Eligibility status and details
    """
    order = get_order.invoke({"order_id": order_id})

    if "error" in order:
        return order

    created_at = order.get("created_at", "")
    fulfillment_status = order.get("fulfillment_status", "")

    try:
        order_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        days_since_order = (datetime.now(timezone.utc) - order_date).days
        eligible = days_since_order <= 30 and fulfillment_status in [
            "fulfilled",
            "partial",
        ]
        return {
            "eligible": eligible,
            "order_id": order_id,
            "days_since_order": days_since_order,
            "fulfillment_status": fulfillment_status,
            "reason": (
                "Within 30-day return window"
                if eligible
                else "Outside return window or not fulfilled"
            ),
        }
    except Exception as e:
        return {"error": f"Failed to check eligibility: {str(e)}"}


# Export all tools
shopify_tools = [get_order, search_orders, create_refund, check_return_eligibility]
