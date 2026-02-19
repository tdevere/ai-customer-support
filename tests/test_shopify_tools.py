"""
Unit tests for Shopify integration tools.

All HTTP calls are mocked — no real Shopify store required.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from shared.config import settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def shopify_settings(monkeypatch):
    """Ensure settings have Shopify credentials for all tests in this module."""
    monkeypatch.setattr(settings, "shopify_api_key", "mock-shopify-token")
    monkeypatch.setattr(settings, "shopify_shop_url", "https://mock.myshopify.com")


def _make_httpx_response(json_body: dict, status_code: int = 200):
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.status_code = status_code
    mock.text = json.dumps(json_body)
    mock.raise_for_status.return_value = None
    return mock


def _recent_order(order_id: str = "12345", days_ago: int = 5) -> dict:
    """Build a mock Shopify order payload that is within the return window."""
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "order": {
            "id": order_id,
            "order_number": 1001,
            "created_at": created.isoformat(),
            "total_price": "99.99",
            "currency": "USD",
            "financial_status": "paid",
            "fulfillment_status": "fulfilled",
            "line_items": [
                {"id": "item1", "title": "Widget", "quantity": 1, "price": "99.99"}
            ],
        }
    }


# ---------------------------------------------------------------------------
# get_order
# ---------------------------------------------------------------------------


def test_get_order_success(mocker):
    """get_order returns parsed order details on 200."""
    from integrations.tools.shopify_tools import get_order

    mock_resp = _make_httpx_response(_recent_order("12345"))
    mocker.patch("integrations.tools.shopify_tools.httpx.get", return_value=mock_resp)

    result = get_order.invoke({"order_id": "12345"})

    assert result["id"] == "12345"
    assert result["financial_status"] == "paid"
    assert result["fulfillment_status"] == "fulfilled"
    assert len(result["line_items"]) == 1


def test_get_order_missing_config(monkeypatch):
    """Returns error dict when Shopify is not configured."""
    from integrations.tools.shopify_tools import get_order

    monkeypatch.setattr(settings, "shopify_api_key", "")

    result = get_order.invoke({"order_id": "12345"})
    assert "error" in result


# ---------------------------------------------------------------------------
# search_orders
# ---------------------------------------------------------------------------


def test_search_orders_success(mocker):
    """search_orders returns a list of order summaries."""
    from integrations.tools.shopify_tools import search_orders

    shopify_response = {
        "orders": [
            {
                "id": "9001",
                "order_number": 2001,
                "created_at": "2025-12-01T10:00:00+00:00",
                "total_price": "49.99",
                "financial_status": "paid",
                "fulfillment_status": "fulfilled",
            },
            {
                "id": "9002",
                "order_number": 2002,
                "created_at": "2026-01-15T10:00:00+00:00",
                "total_price": "29.99",
                "financial_status": "paid",
                "fulfillment_status": "unfulfilled",
            },
        ]
    }
    mock_resp = _make_httpx_response(shopify_response)
    mocker.patch("integrations.tools.shopify_tools.httpx.get", return_value=mock_resp)

    results = search_orders.invoke({"customer_email": "customer@example.com"})

    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0]["id"] == "9001"
    assert results[1]["financial_status"] == "paid"


# ---------------------------------------------------------------------------
# create_refund
# ---------------------------------------------------------------------------


def test_create_refund_success(mocker):
    """create_refund posts to Shopify and returns refund details."""
    from integrations.tools.shopify_tools import create_refund

    refund_response = {
        "refund": {
            "id": "ref_999",
            "order_id": "12345",
            "created_at": "2026-02-01T10:00:00+00:00",
            "note": "customer_request",
            "transactions": [{"id": "tx_1", "amount": "49.99", "kind": "refund"}],
        }
    }
    mock_resp = _make_httpx_response(refund_response)
    mock_post = mocker.patch(
        "integrations.tools.shopify_tools.httpx.post", return_value=mock_resp
    )

    result = create_refund.invoke(
        {"order_id": "12345", "amount": 49.99, "reason": "customer_request"}
    )

    assert result["id"] == "ref_999"
    assert result["order_id"] == "12345"
    assert len(result["transactions"]) == 1
    mock_post.assert_called_once()


# ---------------------------------------------------------------------------
# check_return_eligibility
# ---------------------------------------------------------------------------


def test_check_return_eligibility_eligible(mocker):
    """Orders fulfilled within 30 days should be eligible for return."""
    from integrations.tools.shopify_tools import check_return_eligibility

    mock_resp = _make_httpx_response(_recent_order("12345", days_ago=10))
    mocker.patch("integrations.tools.shopify_tools.httpx.get", return_value=mock_resp)

    result = check_return_eligibility.invoke({"order_id": "12345"})

    assert result["eligible"] is True
    assert result["days_since_order"] <= 30


def test_check_return_eligibility_outside_window(mocker):
    """Orders older than 30 days should not be eligible."""
    from integrations.tools.shopify_tools import check_return_eligibility

    mock_resp = _make_httpx_response(_recent_order("99999", days_ago=45))
    mocker.patch("integrations.tools.shopify_tools.httpx.get", return_value=mock_resp)

    result = check_return_eligibility.invoke({"order_id": "99999"})

    assert result["eligible"] is False
    assert result["days_since_order"] > 30


def test_check_return_eligibility_unfulfilled(mocker):
    """Unfulfilled orders should not be eligible for return."""
    from integrations.tools.shopify_tools import check_return_eligibility

    order = _recent_order("77777", days_ago=2)
    order["order"]["fulfillment_status"] = "unfulfilled"
    mock_resp = _make_httpx_response(order)
    mocker.patch("integrations.tools.shopify_tools.httpx.get", return_value=mock_resp)

    result = check_return_eligibility.invoke({"order_id": "77777"})

    assert result["eligible"] is False
