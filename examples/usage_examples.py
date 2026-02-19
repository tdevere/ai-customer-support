"""
AAN Customer Support System — Usage Examples
=============================================

Runnable code snippets demonstrating key integration patterns.

Prerequisite environment variables (copy from .env.test and fill in real values):

    AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
    AZURE_OPENAI_API_KEY=<key>
    COSMOS_ENDPOINT=https://<your-account>.documents.azure.com:443/
    COSMOS_KEY=<key>
    AZURE_SEARCH_ENDPOINT=https://<your-service>.search.windows.net
    AZURE_SEARCH_KEY=<key>
"""

import asyncio
import uuid

# ---------------------------------------------------------------------------
# Example 1 — Run the AAN orchestrator end-to-end
# ---------------------------------------------------------------------------


async def example_run_orchestrator() -> None:
    """
    Send a customer message through the full AAN pipeline and print the reply.

    The orchestrator:
    1. Checks custom answers for an instant match
    2. Classifies the topic (billing / returns / tech / general)
    3. Dispatches to the appropriate specialist agent
    4. Verifies the response meets a confidence threshold
    5. Escalates to human support if confidence is too low
    """
    from orchestrator.graph import run_aan_orchestrator

    conversation_id = str(uuid.uuid4())

    result = await run_aan_orchestrator(
        conversation_id=conversation_id,
        user_id="customer-42",
        message="I was charged twice for my last order. Can you help?",
        context={
            "channel": "web_chat",
            "customer_tier": "premium",
            "order_id": "ORD-20240512-001",
        },
    )

    print("\n=== Orchestrator result ===")
    print(f"  Status    : {result['status']}")
    print(f"  Agent     : {result.get('agent', 'n/a')}")
    print(f"  Topic     : {result.get('topic', 'n/a')}")
    print(f"  Confidence: {result.get('confidence', 0):.2f}")
    print(f"  Message   :\n{result['message']}")

    if result["status"] == "escalated":
        print(f"\n  Escalation summary: {result.get('escalation_summary', '')}")


# ---------------------------------------------------------------------------
# Example 2 — Custom answers matcher (short-circuit before the LLM pipeline)
# ---------------------------------------------------------------------------


def example_custom_answers_matcher() -> None:
    """
    Check whether a user message matches a hard-coded custom answer.

    Custom answers are defined in agents/custom_answers.yaml.  A match means
    the orchestrator skips topic classification, specialist agents, and the
    verifier entirely — returning the curated answer at the router node.
    """
    from orchestrator.custom_answers import CustomAnswersMatcher

    matcher = CustomAnswersMatcher()

    test_messages = [
        "What are your opening hours?",
        "How do I cancel my subscription?",
        "My widget keeps crashing on iOS 17",
    ]

    print("\n=== Custom Answers Matcher ===")
    for msg in test_messages:
        match = matcher.match(msg)
        if match:
            print(f"  [{match['topic']}] '{msg}' → {match['answer'][:80]}…")
        else:
            print(f"  [no match] '{msg}' → forwarded to LLM pipeline")


# ---------------------------------------------------------------------------
# Example 3 — Conversation memory (Cosmos DB state persistence)
# ---------------------------------------------------------------------------


def example_conversation_memory() -> None:
    """
    Save and retrieve conversation state from Azure Cosmos DB.

    ConversationMemory uses a lazy connection — no network call is made until
    the first actual read/write, so importing it is always safe.

    Note: requires live Cosmos DB credentials to execute.
    """
    from shared.memory import ConversationMemory

    memory = ConversationMemory()
    conversation_id = str(uuid.uuid4())

    state = {
        "user_id": "customer-42",
        "message": "I need to return my order",
        "status": "pending",
        "messages": [],
    }

    print("\n=== ConversationMemory ===")

    # Persist state
    memory.save_state(conversation_id, state)
    print(f"  Saved state for conversation {conversation_id}")

    # Retrieve state
    retrieved = memory.get_state(conversation_id)
    if retrieved:
        print(f"  Retrieved state — status: {retrieved.get('status')}")
    else:
        print("  State not found (expected without live Cosmos DB)")


# ---------------------------------------------------------------------------
# Example 4 — Application Insights telemetry
# ---------------------------------------------------------------------------


def example_telemetry() -> None:
    """
    Emit a custom event and record a metric via the telemetry helper.

    configure_telemetry() is idempotent — call it once at application start.
    All functions are silent no-ops when APPINSIGHTS_CONNECTION_STRING is not set,
    so this example is safe to run locally without an Application Insights resource.
    """
    from shared.telemetry import (
        Timer,
        configure_telemetry,
        get_logger,
        track_event,
        track_metric,
    )

    logger = get_logger(__name__)

    configured = configure_telemetry()
    logger.info("Telemetry enabled: %s", configured)

    track_event(
        "example.run",
        {"script": "usage_examples.py", "env": "local"},
    )

    track_metric("example.counter", 1.0)

    with Timer("example.operation_ms", {"operation": "demo"}):
        # Simulate work
        import time

        time.sleep(0.005)

    print(
        "\n=== Telemetry example executed (no-op if APPINSIGHTS_CONNECTION_STRING is absent) ==="
    )


# ---------------------------------------------------------------------------
# Example 5 — Create individual specialist agents
# ---------------------------------------------------------------------------


def example_create_agents() -> None:
    """
    Instantiate each specialist agent independently.

    Agents are LangGraph StateGraph objects.  In production the orchestrator
    manages them automatically; these examples show how to build and inspect
    them in isolation for debugging or fine-tuning.
    """
    from agents.billing_agent import create_billing_agent
    from agents.returns_agent import create_returns_agent
    from agents.tech_agent import create_tech_agent

    billing = create_billing_agent()
    returns = create_returns_agent()
    tech = create_tech_agent()

    print("\n=== Specialist agents created ===")
    for name, agent in [("billing", billing), ("returns", returns), ("tech", tech)]:
        print(f"  {name}: {type(agent).__name__}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("AAN Customer Support System — Usage Examples")
    print("=" * 60)
    print("Running examples that do not require live Azure credentials...\n")

    # Telemetry (safe no-op without APPINSIGHTS_CONNECTION_STRING)
    example_telemetry()

    # Custom answers matcher (reads local YAML — no credentials needed)
    example_custom_answers_matcher()

    # Agent creation (no credentials needed to construct the graph objects)
    example_create_agents()

    print("\nTo run examples that require live Azure credentials:")
    print("  1. Copy .env.test to .env and fill in real values")
    print("  2. Remove the MOCK prefixes from COSMOS_KEY / AI keys")
    print("  3. Uncomment and call example_run_orchestrator() and")
    print("     example_conversation_memory() in this script\n")

    # Uncomment once live credentials are configured:
    # asyncio.run(example_run_orchestrator())
    # example_conversation_memory()
