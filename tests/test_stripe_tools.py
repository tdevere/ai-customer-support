"""
Unit tests for Stripe integration tools (integrations/tools/stripe_tools.py).

All Stripe API calls are mocked — no real Stripe credentials required.
"""

import pytest
from unittest.mock import MagicMock, patch
import stripe

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stripe_error(msg: str = "stripe error") -> stripe.error.StripeError:
    err = stripe.error.StripeError(msg)
    return err


# ---------------------------------------------------------------------------
# get_customer_info
# ---------------------------------------------------------------------------


class TestGetCustomerInfo:
    def _call(self, customer_id: str):
        from integrations.tools.stripe_tools import get_customer_info

        return get_customer_info.invoke({"customer_id": customer_id})

    def test_returns_customer_fields(self):
        mock_customer = MagicMock()
        mock_customer.id = "cus_123"
        mock_customer.email = "user@example.com"
        mock_customer.name = "Alice"
        mock_customer.balance = 0
        mock_customer.currency = "usd"
        mock_customer.created = 1700000000
        mock_customer.subscriptions.data = [MagicMock(id="sub_abc")]

        with patch("stripe.Customer.retrieve", return_value=mock_customer):
            result = self._call("cus_123")

        assert result["id"] == "cus_123"
        assert result["email"] == "user@example.com"
        assert result["subscriptions"] == ["sub_abc"]

    def test_no_subscriptions_returns_empty_list(self):
        mock_customer = MagicMock()
        mock_customer.id = "cus_456"
        mock_customer.email = "b@b.com"
        mock_customer.name = "Bob"
        mock_customer.balance = 0
        mock_customer.currency = "usd"
        mock_customer.created = 1700000001
        mock_customer.subscriptions = None

        with patch("stripe.Customer.retrieve", return_value=mock_customer):
            result = self._call("cus_456")

        assert result["subscriptions"] == []

    def test_stripe_error_returns_error_dict(self):
        with patch("stripe.Customer.retrieve", side_effect=_stripe_error("not found")):
            result = self._call("cus_bad")

        assert "error" in result


# ---------------------------------------------------------------------------
# get_invoice
# ---------------------------------------------------------------------------


class TestGetInvoice:
    def _call(self, invoice_id: str):
        from integrations.tools.stripe_tools import get_invoice

        return get_invoice.invoke({"invoice_id": invoice_id})

    def test_returns_invoice_fields(self):
        mock_invoice = MagicMock()
        mock_invoice.id = "in_001"
        mock_invoice.number = "INV-001"
        mock_invoice.amount_due = 4900
        mock_invoice.amount_paid = 0
        mock_invoice.currency = "usd"
        mock_invoice.status = "open"
        mock_invoice.due_date = 1700100000
        mock_invoice.hosted_invoice_url = "https://invoice.stripe.com/1"

        with patch("stripe.Invoice.retrieve", return_value=mock_invoice):
            result = self._call("in_001")

        assert result["id"] == "in_001"
        assert result["amount_due"] == 4900
        assert result["status"] == "open"

    def test_stripe_error_returns_error_dict(self):
        with patch("stripe.Invoice.retrieve", side_effect=_stripe_error()):
            result = self._call("in_bad")

        assert "error" in result


# ---------------------------------------------------------------------------
# list_customer_invoices
# ---------------------------------------------------------------------------


class TestListCustomerInvoices:
    def _call(self, customer_id: str, limit: int = 10):
        from integrations.tools.stripe_tools import list_customer_invoices

        return list_customer_invoices.invoke(
            {"customer_id": customer_id, "limit": limit}
        )

    def test_returns_list_of_invoice_summaries(self):
        mock_inv = MagicMock()
        mock_inv.id = "in_002"
        mock_inv.number = "INV-002"
        mock_inv.amount_due = 2900
        mock_inv.status = "paid"
        mock_inv.created = 1700000002

        mock_list = MagicMock()
        mock_list.data = [mock_inv]

        with patch("stripe.Invoice.list", return_value=mock_list):
            result = self._call("cus_789")

        assert len(result) == 1
        assert result[0]["id"] == "in_002"
        assert result[0]["status"] == "paid"

    def test_empty_list(self):
        mock_list = MagicMock()
        mock_list.data = []

        with patch("stripe.Invoice.list", return_value=mock_list):
            result = self._call("cus_empty")

        assert result == []

    def test_stripe_error_returns_list_with_error(self):
        with patch("stripe.Invoice.list", side_effect=_stripe_error()):
            result = self._call("cus_bad")

        assert isinstance(result, list)
        assert "error" in result[0]


# ---------------------------------------------------------------------------
# get_subscription
# ---------------------------------------------------------------------------


class TestGetSubscription:
    def _call(self, subscription_id: str):
        from integrations.tools.stripe_tools import get_subscription

        return get_subscription.invoke({"subscription_id": subscription_id})

    def test_returns_subscription_fields(self):
        mock_sub = MagicMock()
        mock_sub.id = "sub_001"
        mock_sub.status = "active"
        mock_sub.current_period_start = 1700000000
        mock_sub.current_period_end = 1702678400
        mock_sub.plan.nickname = "Pro Monthly"
        mock_sub.plan.amount = 4900
        mock_sub.plan.currency = "usd"

        with patch("stripe.Subscription.retrieve", return_value=mock_sub):
            result = self._call("sub_001")

        assert result["id"] == "sub_001"
        assert result["status"] == "active"
        assert result["plan"] == "Pro Monthly"

    def test_no_plan_returns_none_fields(self):
        mock_sub = MagicMock()
        mock_sub.id = "sub_002"
        mock_sub.status = "canceled"
        mock_sub.current_period_start = 0
        mock_sub.current_period_end = 0
        mock_sub.plan = None

        with patch("stripe.Subscription.retrieve", return_value=mock_sub):
            result = self._call("sub_002")

        assert result["plan"] is None
        assert result["amount"] == 0

    def test_stripe_error_returns_error_dict(self):
        with patch("stripe.Subscription.retrieve", side_effect=_stripe_error()):
            result = self._call("sub_bad")

        assert "error" in result


# ---------------------------------------------------------------------------
# cancel_subscription
# ---------------------------------------------------------------------------


class TestCancelSubscription:
    def _call(self, subscription_id: str, at_period_end: bool = True):
        from integrations.tools.stripe_tools import cancel_subscription

        return cancel_subscription.invoke(
            {"subscription_id": subscription_id, "at_period_end": at_period_end}
        )

    def test_cancel_at_period_end_calls_modify(self):
        mock_sub = MagicMock()
        mock_sub.id = "sub_cancel"
        mock_sub.status = "active"
        mock_sub.cancel_at = 1702678400
        mock_sub.canceled_at = None

        with patch("stripe.Subscription.modify", return_value=mock_sub) as mock_mod:
            result = self._call("sub_cancel", at_period_end=True)

        mock_mod.assert_called_once_with("sub_cancel", cancel_at_period_end=True)
        assert result["id"] == "sub_cancel"

    def test_cancel_immediately_calls_cancel(self):
        mock_sub = MagicMock()
        mock_sub.id = "sub_now"
        mock_sub.status = "canceled"
        mock_sub.cancel_at = None
        mock_sub.canceled_at = 1700000999

        with patch("stripe.Subscription.cancel", return_value=mock_sub) as mock_del:
            result = self._call("sub_now", at_period_end=False)

        mock_del.assert_called_once_with("sub_now")
        assert result["status"] == "canceled"

    def test_stripe_error_returns_error_dict(self):
        with patch("stripe.Subscription.modify", side_effect=_stripe_error()):
            result = self._call("sub_bad")

        assert "error" in result


# ---------------------------------------------------------------------------
# create_payment_intent
# ---------------------------------------------------------------------------


class TestCreatePaymentIntent:
    def _call(self, amount: int, currency: str, customer_id: str):
        from integrations.tools.stripe_tools import create_payment_intent

        return create_payment_intent.invoke(
            {"amount": amount, "currency": currency, "customer_id": customer_id}
        )

    def test_returns_payment_intent_fields(self):
        mock_intent = MagicMock()
        mock_intent.id = "pi_001"
        mock_intent.client_secret = "pi_001_secret_abc"
        mock_intent.amount = 4900
        mock_intent.status = "requires_payment_method"

        with patch("stripe.PaymentIntent.create", return_value=mock_intent):
            result = self._call(4900, "usd", "cus_abc")

        assert result["id"] == "pi_001"
        assert result["client_secret"] == "pi_001_secret_abc"
        assert result["amount"] == 4900

    def test_stripe_error_returns_error_dict(self):
        with patch(
            "stripe.PaymentIntent.create", side_effect=_stripe_error("card_declined")
        ):
            result = self._call(100, "usd", "cus_bad")

        assert "error" in result


# ---------------------------------------------------------------------------
# Tool list export
# ---------------------------------------------------------------------------


def test_stripe_tools_list_has_six_entries():
    from integrations.tools.stripe_tools import stripe_tools

    assert len(stripe_tools) == 6
