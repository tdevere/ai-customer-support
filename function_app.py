"""
Azure Functions HTTP triggers for the AAN Customer Support system.

Routes
------
POST /api/conversations                          – Start a new conversation
POST /api/conversations/{conversation_id}/messages – Reply in existing conversation
GET  /api/conversations/{conversation_id}         – Get conversation state
GET  /api/health                                  – Liveness check
POST /api/webhook                                 – Legacy Intercom webhook (backward compat)
"""

import json
import logging
import uuid

import azure.functions as func

app = func.FunctionApp()

# ---------------------------------------------------------------------------
# Conversations API
# ---------------------------------------------------------------------------


@app.route(
    route="conversations",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def start_conversation(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/conversations
    Start a new conversation and return the first bot response.
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    user_id = body.get("user_id")
    message = body.get("message")
    if not user_id or not message:
        return func.HttpResponse(
            json.dumps({"error": "user_id and message are required"}),
            status_code=422,
            mimetype="application/json",
        )

    conversation_id = str(uuid.uuid4())
    context = body.get("context") or {}
    context["channel"] = body.get("channel", "api")

    from orchestrator.graph import run_aan_orchestrator

    result = await run_aan_orchestrator(
        conversation_id=conversation_id,
        user_id=user_id,
        message=message,
        context=context,
    )

    return func.HttpResponse(
        json.dumps({"conversation_id": conversation_id, **result}),
        status_code=201,
        mimetype="application/json",
    )


@app.route(
    route="conversations/{conversation_id}/messages",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def reply_to_conversation(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/conversations/{conversation_id}/messages
    Send a follow-up message in an existing conversation.
    """
    conversation_id = req.route_params.get("conversation_id")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    message = body.get("message")
    if not message:
        return func.HttpResponse(
            json.dumps({"error": "message is required"}),
            status_code=422,
            mimetype="application/json",
        )

    from orchestrator.graph import run_aan_orchestrator

    result = await run_aan_orchestrator(
        conversation_id=conversation_id,
        user_id=body.get("user_id", "anonymous"),
        message=message,
        context=body.get("context") or {},
    )

    return func.HttpResponse(
        json.dumps({"conversation_id": conversation_id, **result}),
        status_code=200,
        mimetype="application/json",
    )


@app.route(
    route="conversations/{conversation_id}",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_conversation(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/conversations/{conversation_id}
    Retrieve the last persisted state of a conversation.
    """
    conversation_id = req.route_params.get("conversation_id")

    from shared.memory import memory

    state = memory.get_state(conversation_id)
    if not state:
        return func.HttpResponse(
            json.dumps({"error": f"Conversation '{conversation_id}' not found"}),
            status_code=404,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({"conversation_id": conversation_id, **state}),
        status_code=200,
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/health — liveness check."""
    return func.HttpResponse(
        json.dumps({"status": "healthy", "service": "AAN Customer Support"}),
        status_code=200,
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# Legacy Intercom webhook (kept for backward compatibility)
# ---------------------------------------------------------------------------


@app.route(route="webhook", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def webhook_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/webhook — legacy Intercom webhook handler.

    Validates HMAC signature and routes to the AAN orchestrator.
    New integrations should use POST /api/conversations instead.
    """
    logging.info("Webhook trigger received")

    try:
        body = req.get_body()
        signature = req.headers.get("X-Hub-Signature-256") or req.headers.get(
            "X-Intercom-Signature"
        )

        from integrations.intercom import validate_webhook_signature
        from shared.config import settings

        if not validate_webhook_signature(
            body, signature, settings.intercom_webhook_secret
        ):
            logging.warning("Invalid webhook signature")
            return func.HttpResponse(
                json.dumps({"error": "Invalid signature"}),
                status_code=403,
                mimetype="application/json",
            )

        payload = json.loads(body)
        topic = payload.get("topic")
        data = payload.get("data", {})
        item = data.get("item", {})

        logging.info(f"Processing webhook topic: {topic}")

        if topic in ["conversation.user.replied", "conversation.user.created"]:
            conversation_id = item.get("id")
            user_message = item.get("conversation_message", {}).get("body", "")
            user_id = item.get("user", {}).get("id")

            from orchestrator.graph import run_aan_orchestrator

            result = await run_aan_orchestrator(
                conversation_id=conversation_id,
                user_id=user_id,
                message=user_message,
                context=item,
            )

            logging.info(f'Orchestrator result: {result.get("status")}')

            if result.get("status") == "success":
                from integrations.intercom import post_reply_to_intercom

                await post_reply_to_intercom(
                    conversation_id=conversation_id,
                    message=result.get("message", ""),
                )
            elif result.get("status") == "escalated":
                from integrations.intercom import add_note_to_intercom

                await add_note_to_intercom(
                    conversation_id=conversation_id,
                    note=result.get("escalation_summary", "Escalated by AAN"),
                )

        return func.HttpResponse(
            json.dumps({"status": "ok"}),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )
