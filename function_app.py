"""
Azure Functions HTTP trigger for webhook endpoint.
"""
import azure.functions as func
import json
import logging
from integrations.intercom import intercom_webhook

app = func.FunctionApp()


@app.route(route="webhook", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def webhook_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger for Intercom webhook.
    
    This function receives webhooks from Intercom and processes them
    through the AAN orchestrator.
    """
    logging.info('Webhook trigger received')
    
    try:
        # Get raw body and headers
        body = req.get_body()
        signature = req.headers.get('X-Hub-Signature-256') or req.headers.get('X-Intercom-Signature')
        
        # Import FastAPI app's webhook handler
        from integrations.intercom import validate_webhook_signature, settings
        
        # Validate signature
        if not validate_webhook_signature(body, signature, settings.intercom_webhook_secret):
            logging.warning('Invalid webhook signature')
            return func.HttpResponse(
                "Invalid signature",
                status_code=403
            )
        
        # Parse payload
        payload = json.loads(body)
        
        # Process webhook
        topic = payload.get('topic')
        data = payload.get('data', {})
        item = data.get('item', {})
        
        logging.info(f'Processing webhook topic: {topic}')
        
        if topic in ['conversation.user.replied', 'conversation.user.created']:
            conversation_id = item.get('id')
            user_message = item.get('conversation_message', {}).get('body', '')
            user_id = item.get('user', {}).get('id')
            
            # Import and run orchestrator
            from orchestrator.graph import run_aan_orchestrator
            
            result = await run_aan_orchestrator(
                conversation_id=conversation_id,
                user_id=user_id,
                message=user_message,
                context=item
            )
            
            logging.info(f'Orchestrator result: {result.get("status")}')
            
            # Post response if successful
            if result.get('status') == 'success':
                from integrations.intercom import post_reply_to_intercom
                await post_reply_to_intercom(
                    conversation_id=conversation_id,
                    message=result.get('message', '')
                )
            elif result.get('status') == 'escalated':
                from integrations.intercom import add_note_to_intercom
                await add_note_to_intercom(
                    conversation_id=conversation_id,
                    note=result.get('escalation_summary', 'Escalated by AAN')
                )
        
        return func.HttpResponse(
            json.dumps({"status": "ok"}),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.error(f'Error processing webhook: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    return func.HttpResponse(
        json.dumps({"status": "healthy", "service": "AAN Customer Support"}),
        status_code=200,
        mimetype="application/json"
    )
