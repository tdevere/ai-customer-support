"""
Stripe integration tools for billing agent.
"""
from typing import Dict, Any, List, Optional
import stripe
from langchain_core.tools import tool
from shared.config import settings

# Configure Stripe
stripe.api_key = settings.stripe_api_key


@tool
def get_customer_info(customer_id: str) -> Dict[str, Any]:
    """
    Retrieve customer information from Stripe.
    
    Args:
        customer_id: Stripe customer ID
        
    Returns:
        Customer details including email, payment methods, subscriptions
    """
    try:
        customer = stripe.Customer.retrieve(customer_id)
        return {
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "balance": customer.balance,
            "currency": customer.currency,
            "created": customer.created,
            "subscriptions": [sub.id for sub in customer.subscriptions.data] if customer.subscriptions else []
        }
    except stripe.error.StripeError as e:
        return {"error": str(e)}


@tool
def get_invoice(invoice_id: str) -> Dict[str, Any]:
    """
    Retrieve invoice details from Stripe.
    
    Args:
        invoice_id: Stripe invoice ID
        
    Returns:
        Invoice details including amount, status, due date
    """
    try:
        invoice = stripe.Invoice.retrieve(invoice_id)
        return {
            "id": invoice.id,
            "number": invoice.number,
            "amount_due": invoice.amount_due,
            "amount_paid": invoice.amount_paid,
            "currency": invoice.currency,
            "status": invoice.status,
            "due_date": invoice.due_date,
            "hosted_invoice_url": invoice.hosted_invoice_url
        }
    except stripe.error.StripeError as e:
        return {"error": str(e)}


@tool
def list_customer_invoices(customer_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    List all invoices for a customer.
    
    Args:
        customer_id: Stripe customer ID
        limit: Maximum number of invoices to return (default: 10)
        
    Returns:
        List of invoice summaries
    """
    try:
        invoices = stripe.Invoice.list(customer=customer_id, limit=limit)
        return [{
            "id": inv.id,
            "number": inv.number,
            "amount_due": inv.amount_due,
            "status": inv.status,
            "created": inv.created
        } for inv in invoices.data]
    except stripe.error.StripeError as e:
        return [{"error": str(e)}]


@tool
def get_subscription(subscription_id: str) -> Dict[str, Any]:
    """
    Retrieve subscription details from Stripe.
    
    Args:
        subscription_id: Stripe subscription ID
        
    Returns:
        Subscription details including plan, status, billing cycle
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        return {
            "id": subscription.id,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "plan": subscription.plan.nickname if subscription.plan else None,
            "amount": subscription.plan.amount if subscription.plan else 0,
            "currency": subscription.plan.currency if subscription.plan else None
        }
    except stripe.error.StripeError as e:
        return {"error": str(e)}


@tool
def cancel_subscription(subscription_id: str, at_period_end: bool = True) -> Dict[str, Any]:
    """
    Cancel a Stripe subscription.
    
    Args:
        subscription_id: Stripe subscription ID
        at_period_end: If True, cancel at end of billing period (default: True)
        
    Returns:
        Cancellation confirmation
    """
    try:
        if at_period_end:
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
        else:
            subscription = stripe.Subscription.cancel(subscription_id)
        
        return {
            "id": subscription.id,
            "status": subscription.status,
            "cancel_at": subscription.cancel_at,
            "canceled_at": subscription.canceled_at
        }
    except stripe.error.StripeError as e:
        return {"error": str(e)}


@tool
def create_payment_intent(amount: int, currency: str, customer_id: str) -> Dict[str, Any]:
    """
    Create a payment intent for manual payment.
    
    Args:
        amount: Amount in cents
        currency: Currency code (e.g., 'usd')
        customer_id: Stripe customer ID
        
    Returns:
        Payment intent with client secret
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            customer=customer_id,
            automatic_payment_methods={"enabled": True}
        )
        return {
            "id": intent.id,
            "client_secret": intent.client_secret,
            "amount": intent.amount,
            "status": intent.status
        }
    except stripe.error.StripeError as e:
        return {"error": str(e)}


# Export all tools
stripe_tools = [
    get_customer_info,
    get_invoice,
    list_customer_invoices,
    get_subscription,
    cancel_subscription,
    create_payment_intent
]
