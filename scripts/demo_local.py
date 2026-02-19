"""
scripts/demo_local.py
─────────────────────
Starts the Customer Support API with ALL Azure dependencies mocked.
No real Azure credentials required.

How it works
------------
1. Fake environment variables are injected so LangChain / Cosmos / Search
   objects initialise successfully (they validate nothing at init time).
2. The module-level memory and rag singletons are monkey-patched with
   in-memory replacements so no network calls are made.
3. The core orchestrator entry-point (run_aan_orchestrator) is replaced
   with a keyword-routing mock that returns realistic scripted responses.
4. uvicorn serves the FastAPI app on http://localhost:8000.

Usage (from repo root)
----------------------
    # Start the server (keep this terminal open):
    .venv\\Scripts\\python.exe scripts/demo_local.py

    # Then, in a second terminal, run the guided demo:
    .\\scripts\\demo.ps1

    # Or browse the interactive Swagger docs:
    http://localhost:8000/docs
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import patch

# ── Repo root on path ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Inject fake Azure credentials BEFORE any app module is imported ──────────
# LangChain, azure-cosmos, and azure-search don't validate credentials at
# object construction time, but some require non-empty strings.
_DEMO_ENV = {
    "AZURE_OPENAI_ENDPOINT": "https://demo-local.openai.azure.com/",
    "AZURE_OPENAI_API_KEY": "sk-demo-0000000000000000000000000000000000000000",
    "AZURE_OPENAI_DEPLOYMENT_GPT4": "gpt-4o",
    "AZURE_OPENAI_DEPLOYMENT_GPT4_MINI": "gpt-4o-mini",
    "COSMOS_ENDPOINT": "https://demo-local.documents.azure.com:443/",
    "COSMOS_KEY": "ZGVtby1rZXktbm90LXJlYWw=",
    "AZURE_SEARCH_ENDPOINT": "https://demo-local.search.windows.net",
    "AZURE_SEARCH_KEY": "demo-search-key-not-real",
    "APPINSIGHTS_CONNECTION_STRING": "",  # telemetry stays no-op
    "STRIPE_API_KEY": "",
    "JIRA_BASE_URL": "",
    "JIRA_EMAIL": "",
    "JIRA_API_TOKEN": "",
    "SHOPIFY_SHOP_URL": "",
    "SHOPIFY_API_KEY": "",
    "SUPPORT_API_KEY": "",  # auth disabled for demo
    "ENVIRONMENT": "demo",
}
for k, v in _DEMO_ENV.items():
    os.environ.setdefault(k, v)


# ── In-memory conversation store (replaces Cosmos DB) ────────────────────────
_memory_store: Dict[str, Dict[str, Any]] = {}


# ── Scripted orchestrator mock ────────────────────────────────────────────────
async def _mock_run_orchestrator(
    conversation_id: str,
    user_id: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Route on message keywords and return a realistic scripted response.
    The real LangGraph / LLM pipeline is entirely bypassed.
    """
    msg = message.lower()

    # ── Resolution / thank-you ────────────────────────────────────────────────
    if any(
        w in msg
        for w in [
            "thanks",
            "thank you",
            "thx",
            "ty",
            "solved",
            "fixed",
            "all good",
            "works now",
            "great",
            "perfect",
            "awesome",
            "sorted",
        ]
    ):
        response = (
            "You're welcome! Really glad that sorted things out. "
            "If anything else comes up, we're always here — just message us. "
            "Have a great day! 🎉"
        )
        topic = "general"
        resolution = "resolved_confirmed"

    # ── Billing / payment ─────────────────────────────────────────────────────
    elif any(
        w in msg
        for w in [
            "charge",
            "charges",
            "invoice",
            "payment",
            "billing",
            "refund",
            "subscription",
            "billed",
            "cost",
            "price",
            "fee",
        ]
    ):
        response = (
            "Thank you for contacting us about your billing concern.\n\n"
            "I've pulled up your account and can see your billing history. "
            "Your most recent invoice was processed on **February 1, 2026** for **$49.00**. "
            "If you believe there's a discrepancy, I can open a billing dispute immediately — "
            "refunds are typically credited back within **5–7 business days**.\n\n"
            "Would you like me to initiate a dispute? Or if you can share the specific "
            "charge reference, I can look into it in more detail right now."
        )
        topic = "billing"
        resolution = "resolved_assumed"

    # ── Technical issue ───────────────────────────────────────────────────────
    elif any(
        w in msg
        for w in [
            "crash",
            "crashing",
            "error",
            "bug",
            "broken",
            "not working",
            "freezes",
            "won't load",
            "login",
            "log in",
            "sign in",
            "slow",
            "app",
        ]
    ):
        response = (
            "I'm sorry you're running into this — let's get it fixed.\n\n"
            "**Try these steps first:**\n"
            "1. Force-close the app completely and reopen it\n"
            "2. Go to **Settings → Advanced → Clear Cache**\n"
            "3. Make sure you're on the latest version (**v4.2.1** — available in your app store)\n"
            "4. If the issue persists, uninstall and reinstall the app\n\n"
            "I've also checked our status page — **no active incidents** are reported right now. "
            "If none of the above works, reply here with your device model and OS version "
            "and I'll escalate to our engineering team straight away."
        )
        topic = "tech"
        resolution = "resolved_assumed"

    # ── Returns / shipping ────────────────────────────────────────────────────
    elif any(
        w in msg
        for w in [
            "return",
            "returns",
            "shipping",
            "ship",
            "delivery",
            "deliver",
            "track",
            "tracking",
            "order",
            "package",
            "arrived",
            "missing",
        ]
    ):
        response = (
            "Happy to help with your order!\n\n"
            "Our **30-day return policy** covers any unused item in its original packaging. "
            "Here's how to start a return:\n"
            "1. Log in and go to **Account → Orders**\n"
            "2. Select your order → click **Request Return**\n"
            "3. A prepaid shipping label will be emailed to you within 10 minutes\n\n"
            "Refunds are credited to your original payment method within **5–7 business days** "
            "after we receive the item.\n\n"
            "If your package hasn't arrived yet, I can open a trace with the carrier — "
            "just let me know your order number."
        )
        topic = "returns"
        resolution = "resolved_assumed"

    # ── General / catch-all ───────────────────────────────────────────────────
    else:
        response = (
            "Thanks for reaching out — I'm here to help!\n\n"
            "To point you in the right direction, could you share a bit more detail? "
            "For example:\n"
            "- Is this a **billing or payment** question?\n"
            "- A **technical issue** with the app or platform?\n"
            "- A **return or delivery** question?\n\n"
            "Just let me know and I'll get you sorted."
        )
        topic = "general"
        resolution = "resolved_assumed"

    # Persist to in-memory store so GET /conversations/{id} works
    _memory_store[conversation_id] = {
        "response": response,
        "status": "success",
        "confidence": 0.88,
        "classification": {"primary_topic": topic},
        "resolution_state": resolution,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "status": "success",
        "message": response,
        "confidence": 0.88,
        "sources": [],
        "escalation_summary": None,
        "agent": topic,
        "topic": topic,
        "resolution_state": resolution,
        "custom_answer_used": False,
        "handoff_summary": "",
    }


# ── Apply patches and start server ───────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # Import singletons AFTER env vars are set so Settings() picks them up
    import shared.memory as mem_module  # noqa: E402
    import shared.rag as rag_module  # noqa: E402

    # Patch the memory singleton so Cosmos DB is never contacted
    mem_module.memory.get_state = lambda conv_id: _memory_store.get(conv_id)  # type: ignore[method-assign]
    mem_module.memory.load_state = lambda conv_id: _memory_store.get(conv_id)  # type: ignore[method-assign]
    mem_module.memory.save_state = lambda conv_id, state: _memory_store.update(  # type: ignore[method-assign]
        {conv_id: state}
    )
    mem_module.memory._ensure_connected = lambda: None  # type: ignore[method-assign]

    # Patch the RAG singleton so Azure AI Search is never contacted
    rag_module.rag._ensure_connected = lambda: None  # type: ignore[method-assign]
    rag_module.rag.retrieve_context = lambda *args, **kwargs: [  # type: ignore[method-assign]
        {
            "id": "kb-001",
            "title": "Billing FAQ",
            "content": (
                "Our billing cycle is monthly. Charges appear within 24 hours. "
                "Refunds take 5–7 business days."
            ),
            "score": 0.92,
            "topic": "billing",
        },
        {
            "id": "kb-002",
            "title": "Technical Troubleshooting Guide",
            "content": (
                "Common fixes: clear cache, update the app, reinstall. "
                "Engineering tickets can be raised via the support chat."
            ),
            "score": 0.88,
            "topic": "tech",
        },
    ]

    # Patch the orchestrator entry-point so no LLM calls are made
    with patch("orchestrator.graph.run_aan_orchestrator", new=_mock_run_orchestrator):
        print()
        print("=" * 62)
        print("  AAN Customer Support API  —  LOCAL DEMO MODE")
        print("  All Azure services are MOCKED  (no cloud calls)")
        print("=" * 62)
        print()
        print("  Swagger UI :  http://localhost:8000/docs")
        print("  Health     :  http://localhost:8000/health")
        print()
        print("  Run the guided demo in a second terminal:")
        print("    .\\scripts\\demo.ps1")
        print()
        print("  Press Ctrl+C to stop.")
        print()

        uvicorn.run(
            "integrations.conversations:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="warning",
        )
