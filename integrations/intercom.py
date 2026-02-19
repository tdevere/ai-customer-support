"""
Intercom webhook handler and API integration.
Handles incoming webhooks, validates signatures, and posts responses.
"""

import hmac
import hashlib
import json
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
import httpx
from shared.config import settings

app = FastAPI(title="AAN Intercom Integration")


def validate_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """
    Validate Intercom webhook signature using HMAC SHA256.

    Args:
        body: Raw request body
        signature: Signature from X-Hub-Signature-256 or similar header
        secret: Webhook secret

    Returns:
        True if signature is valid
    """
    if not signature or not secret:
        return False

    # Intercom uses sha256=<hash> format
    if signature.startswith("sha256="):
        signature = signature[7:]

    # Compute expected signature
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected, signature)


@app.post("/webhook")
async def intercom_webhook(request: Request):
    """
    Handle incoming Intercom webhooks.
    Validates signature and triggers AAN orchestrator.

    Expected topics:
    - conversation.user.replied (user sends message)
    - conversation.admin.replied (agent/bot replies)
    - fin.handoff (Fin hands off to specialist)
    """
    # Read raw body for signature validation
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256") or request.headers.get(
        "X-Intercom-Signature"
    )

    # Validate signature
    if not validate_webhook_signature(
        body, signature, settings.intercom_webhook_secret
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook signature"
        )

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
        )

    # Extract conversation details
    topic = payload.get("topic")
    data = payload.get("data", {})
    item = data.get("item", {})

    # Handle different webhook types
    if topic in ["conversation.user.replied", "conversation.user.created"]:
        conversation_id = item.get("id")
        user_message = item.get("conversation_message", {}).get("body", "")
        user_id = item.get("user", {}).get("id")

        # Import here to avoid circular dependency
        from orchestrator.graph import run_aan_orchestrator

        # Run orchestrator asynchronously
        result = await run_aan_orchestrator(
            conversation_id=conversation_id,
            user_id=user_id,
            message=user_message,
            context=item,
        )

        # Post response back to Intercom if successful
        if (
            result.get("status") == "success"
            and result.get("confidence", 0) >= settings.confidence_threshold
        ):
            await post_reply_to_intercom(
                conversation_id=conversation_id,
                message=result.get("message", ""),
                admin_id=result.get("admin_id"),
            )
        elif result.get("status") == "escalated":
            # Add note for human agent
            await add_note_to_intercom(
                conversation_id=conversation_id,
                note=result.get("escalation_summary", "Escalated by AAN system"),
            )

    return JSONResponse({"status": "ok"})


@app.post("/data-connector")
async def data_connector_endpoint(request: Request):
    """
    Handle Fin data connector requests.
    Alternative integration point for Fin workflows.
    """
    body = await request.body()
    payload = json.loads(body)

    # Extract Fin request data
    conversation_id = payload.get("conversation_id")
    query = payload.get("query", "")
    context = payload.get("context", {})

    # Import here to avoid circular dependency
    from orchestrator.graph import run_aan_orchestrator

    # Run orchestrator
    result = await run_aan_orchestrator(
        conversation_id=conversation_id,
        user_id=context.get("user_id"),
        message=query,
        context=context,
    )

    # Return formatted response for Fin
    return JSONResponse(
        {
            "response": result.get("message", ""),
            "confidence": result.get("confidence", 0),
            "sources": result.get("sources", []),
            "metadata": {
                "agent": result.get("agent", "unknown"),
                "topic": result.get("topic", "unknown"),
            },
        }
    )


async def post_reply_to_intercom(
    conversation_id: str, message: str, admin_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Post a reply to an Intercom conversation as an admin.

    Args:
        conversation_id: Intercom conversation ID
        message: Reply message
        admin_id: Optional admin ID (defaults to app bot)

    Returns:
        API response
    """
    url = f"https://api.intercom.io/conversations/{conversation_id}/reply"
    headers = {
        "Authorization": f"Bearer {settings.intercom_access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {"message_type": "comment", "type": "admin", "body": message}

    if admin_id:
        payload["admin_id"] = admin_id

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, json=payload, headers=headers, timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"Error posting to Intercom: {e}")
            raise


async def add_note_to_intercom(conversation_id: str, note: str) -> Dict[str, Any]:
    """
    Add an internal note to an Intercom conversation.

    Args:
        conversation_id: Intercom conversation ID
        note: Note content

    Returns:
        API response
    """
    url = f"https://api.intercom.io/conversations/{conversation_id}/reply"
    headers = {
        "Authorization": f"Bearer {settings.intercom_access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {"message_type": "note", "type": "admin", "body": note}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, json=payload, headers=headers, timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"Error posting note to Intercom: {e}")
            raise


async def get_conversation_from_intercom(conversation_id: str) -> Dict[str, Any]:
    """
    Retrieve full conversation details from Intercom.

    Args:
        conversation_id: Intercom conversation ID

    Returns:
        Conversation data
    """
    url = f"https://api.intercom.io/conversations/{conversation_id}"
    headers = {
        "Authorization": f"Bearer {settings.intercom_access_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"Error fetching conversation from Intercom: {e}")
            raise
