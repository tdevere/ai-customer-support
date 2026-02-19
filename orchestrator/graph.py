"""
Main LangGraph orchestrator for the AAN system.
Coordinates topic classification, specialist routing, verification, and escalation.

Graph flow
----------
    check_custom_answers
        ├─ custom_match  ──────────────────────────────────────► respond
        └─ no_match ──► classify ──► route_specialists ──► verify
                                                              ├─ respond ──► END
                                                              └─ summarize ──► escalate ──► END
"""

import importlib
from typing import Dict, Any, List, Literal, Optional
from typing_extensions import TypedDict
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from orchestrator.supervisor import classifier
from orchestrator.verifier import verifier
from orchestrator.escalator import escalator
from orchestrator.custom_answers import custom_answers_matcher
from shared.memory import memory
from shared.config import settings

# ---------------------------------------------------------------------------
# Resolution state
# ---------------------------------------------------------------------------

# Mirrors Intercom Fin's outcome-tracking taxonomy:
#   resolved_assumed   – bot answered confidently; customer went quiet (default)
#   resolved_confirmed – customer explicitly acknowledged resolution
#   escalated          – handed off to human agent
#   in_progress        – multi-turn; not yet resolved
ResolutionState = Literal[
    "in_progress",
    "resolved_assumed",
    "resolved_confirmed",
    "escalated",
]

# Phrases that indicate the customer confirmed the issue is resolved
_CONFIRMATION_PHRASES = {
    "thank",
    "thanks",
    "thank you",
    "thx",
    "ty",
    "solved",
    "fixed",
    "resolved",
    "sorted",
    "perfect",
    "great",
    "awesome",
    "excellent",
    "got it",
    "got that",
    "all good",
    "works now",
    "that worked",
    "problem solved",
    "issue resolved",
    "no further",
    "never mind",
    "all set",
}


def _detect_confirmation(message: str) -> bool:
    """Return True if *message* looks like a customer confirming resolution."""
    lowered = message.lower()
    return any(phrase in lowered for phrase in _CONFIRMATION_PHRASES)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class OrchestratorState(TypedDict):
    """Main state for the orchestrator graph."""

    conversation_id: str
    user_id: str
    message: str
    context: Dict[str, Any]
    classification: Dict[str, Any]
    specialist_responses: List[Dict[str, Any]]
    verification: Dict[str, Any]
    final_response: str
    final_confidence: float
    status: str
    escalation: Dict[str, Any]
    sources: List[Dict[str, Any]]
    # New fields
    resolution_state: str  # see ResolutionState
    custom_answer_id: str  # non-empty when a custom answer fired
    handoff_summary: str  # LLM-generated escalation summary


# ---------------------------------------------------------------------------
# Node: check_custom_answers  (before classify – can short-circuit entirely)
# ---------------------------------------------------------------------------


def check_custom_answers_node(state: OrchestratorState) -> OrchestratorState:
    """
    Test the user message against the custom-answers override layer.

    If a match is found the response is written directly into the state and
    ``custom_answer_id`` is populated so the conditional edge can route
    straight to ``respond`` without touching the LLM pipeline.
    """
    match = custom_answers_matcher.match(state["message"])

    if match:
        state["custom_answer_id"] = match["id"]
        state["final_response"] = match["answer"]
        state["final_confidence"] = match["confidence"]
        state["classification"] = {
            "primary_topic": match["topic"],
            "primary_confidence": match["confidence"],
            "all_topics": [
                {"topic": match["topic"], "confidence": match["confidence"]}
            ],
            "source": "custom_answers",
        }
        print(f"Custom answer matched: {match['id']} (topic={match['topic']})")
    else:
        state["custom_answer_id"] = ""

    return state


def decide_after_custom_answers(state: OrchestratorState) -> str:
    """Route to 'respond' if a custom answer matched, otherwise 'classify'."""
    return "respond" if state.get("custom_answer_id") else "classify"


# ---------------------------------------------------------------------------
# Node: classify
# ---------------------------------------------------------------------------


def classify_topic_node(state: OrchestratorState) -> OrchestratorState:
    """
    Classify the user query into topics.
    """
    message = state["message"]

    # Classify query
    classification = classifier.classify(message)
    state["classification"] = classification

    print(f"Classification: {classification}")
    return state


def route_to_specialists_node(state: OrchestratorState) -> OrchestratorState:
    """
    Route to appropriate specialist agents based on classification.
    """
    classification = state["classification"]
    all_topics = [t["topic"] for t in classification.get("all_topics", [])]

    # Get primary topic at minimum
    if not all_topics:
        all_topics = [classification.get("primary_topic", "general")]

    # Get agent configurations
    agent_configs = classifier.get_agent_configs(all_topics)

    specialist_responses = []

    # Execute each specialist agent
    for config in agent_configs:
        topic = config["topic"]
        module_name = config.get("module", f"agents.{topic}_agent")
        agent_name = config.get("agent_name", f"{topic}_agent")

        try:
            # Dynamically import agent
            module = importlib.import_module(module_name)
            agent = getattr(module, agent_name)

            # Prepare agent input
            agent_input = {
                "query": state["message"],
                "messages": [HumanMessage(content=state["message"])],
                "user_id": state.get("user_id", ""),
                "customer_id": state.get("context", {}).get("customer_id", ""),
                "order_id": state.get("context", {}).get("order_id", ""),
                "customer_email": state.get("context", {}).get("customer_email", ""),
            }

            # Invoke agent
            result = agent.invoke(agent_input)

            specialist_responses.append(
                {
                    "agent": topic,
                    "response": result.get("response", ""),
                    "confidence": result.get("confidence", 0.5),
                    "sources": result.get("sources", []),
                    "tool_results": result.get("tool_results", []),
                }
            )

            print(
                f"Agent {topic} responded with confidence {result.get('confidence', 0.5)}"
            )

        except Exception as e:
            print(f"Error executing agent {topic}: {e}")
            specialist_responses.append(
                {
                    "agent": topic,
                    "response": f"Error: Unable to process with {topic} agent",
                    "confidence": 0.0,
                    "sources": [],
                    "tool_results": [],
                }
            )

    state["specialist_responses"] = specialist_responses
    return state


def verify_response_node(state: OrchestratorState) -> OrchestratorState:
    """
    Verify specialist responses using the verifier agent.
    """
    specialist_responses = state["specialist_responses"]

    if not specialist_responses:
        state["verification"] = {
            "final_confidence": 0.0,
            "should_escalate": True,
            "critique": "No specialist responses available",
        }
        return state

    # Use the highest confidence response
    best_response = max(specialist_responses, key=lambda x: x.get("confidence", 0))

    # Verify the response
    verification = verifier.verify(
        query=state["message"],
        response=best_response["response"],
        sources=best_response.get("sources", []),
        agent_confidence=best_response["confidence"],
        tool_results=best_response.get("tool_results", []),
    )

    state["verification"] = verification
    state["final_response"] = best_response["response"]
    state["final_confidence"] = verification["final_confidence"]
    state["sources"] = best_response.get("sources", [])

    print(
        f"Verification: confidence={verification['final_confidence']}, should_escalate={verification.get('should_escalate', False)}"
    )

    return state


def decide_escalation(state: OrchestratorState) -> str:
    """
    Decide whether to respond or escalate based on verification.
    """
    verification = state.get("verification", {})

    if verification.get("should_escalate", False):
        return "escalate"
    else:
        return "respond"


def respond_node(state: OrchestratorState) -> OrchestratorState:
    """
    Prepare a successful response and set resolution state.

    Resolution state follows Intercom Fin's outcome model:
    - resolved_confirmed  – customer's message contains thanks/confirmation
    - resolved_assumed    – bot answered confidently (default on first response)
    """
    state["status"] = "success"

    # Determine resolution state
    if _detect_confirmation(state["message"]):
        state["resolution_state"] = "resolved_confirmed"
    else:
        state["resolution_state"] = "resolved_assumed"

    # Persist to Cosmos DB
    memory.save_state(
        state["conversation_id"],
        {
            "message": state["message"],
            "response": state["final_response"],
            "confidence": state["final_confidence"],
            "classification": state["classification"],
            "resolution_state": state["resolution_state"],
            "custom_answer_id": state.get("custom_answer_id", ""),
            "timestamp": "now",
        },
    )

    print(
        f"Responding with confidence {state['final_confidence']}, "
        f"resolution={state['resolution_state']}"
    )

    return state


def summarize_node(state: OrchestratorState) -> OrchestratorState:
    """
    Generate a structured AI-powered handoff summary before escalation.

    Equivalent to Intercom Fin's "AI Summarize" feature – gives the human
    agent instant context without having to read the full conversation.

    The summary is stored in ``state['handoff_summary']`` and is included in
    the escalation payload returned to the caller.
    Falls back to a plain-text template if the LLM call fails.
    """
    query = state["message"]
    verification = state.get("verification", {})
    specialist_responses = state.get("specialist_responses", [])

    try:
        from langchain_openai import AzureChatOpenAI

        llm = AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_deployment=settings.azure_openai_deployment_gpt4_mini,
            temperature=0,
        )

        agents_tried = (
            ", ".join(r.get("agent", "unknown") for r in specialist_responses) or "none"
        )
        best_confidence = max(
            (r.get("confidence", 0) for r in specialist_responses), default=0
        )

        prompt = (
            "You are a customer support handoff assistant.  Write a concise, "
            "structured summary for the human agent who is about to take over "
            "this conversation.  Include:\n"
            "1. Customer issue (one sentence)\n"
            "2. What was already attempted\n"
            "3. Why it needs human attention\n"
            "4. Suggested next action\n\n"
            f"Customer message: {query}\n"
            f"Agents tried: {agents_tried}\n"
            f"Best confidence reached: {best_confidence:.0%}\n"
            f"Verifier notes: {verification.get('critique', 'N/A')}"
        )

        response = llm.invoke([SystemMessage(content=prompt)])
        state["handoff_summary"] = response.content.strip()

    except Exception as exc:
        # Fallback: use the structured string from escalator
        print(f"Summarize LLM call failed, using template fallback: {exc}")
        state["handoff_summary"] = (
            f"CUSTOMER ISSUE: {query}\n"
            f"AGENTS TRIED: {', '.join(r.get('agent','?') for r in specialist_responses) or 'none'}\n"
            f"VERIFIER NOTES: {verification.get('critique', 'Low confidence')}\n"
            f"ACTION: Manual review required"
        )

    print("Handoff summary generated.")
    return state


def escalate_node(state: OrchestratorState) -> OrchestratorState:
    """
    Escalate to human agent, incorporating the AI-generated handoff summary.
    """
    escalation = escalator.escalate(
        conversation_id=state["conversation_id"],
        query=state["message"],
        attempted_responses=state["specialist_responses"],
        verification_result=state["verification"],
        user_context=state.get("context", {}),
    )

    state["status"] = "escalated"
    state["escalation"] = escalation
    state["resolution_state"] = "escalated"

    # Merge the AI-generated handoff summary into the escalation payload
    handoff_summary = state.get("handoff_summary", "")
    if handoff_summary:
        state["escalation"]["handoff_summary"] = handoff_summary

    # Persist to Cosmos DB
    memory.save_state(
        state["conversation_id"],
        {
            "message": state["message"],
            "escalation": escalation,
            "classification": state["classification"],
            "resolution_state": state["resolution_state"],
            "handoff_summary": handoff_summary,
            "timestamp": "now",
        },
    )

    print(f"Escalated: {escalation.get('escalation_reason', 'Unknown reason')}")

    return state


def create_orchestrator_graph():
    """
    Create the main orchestrator graph.

    Flow:
        check_custom_answers
            ├─ custom_match ──────────────────────────────► respond
            └─ no_match ──► classify ──► route_specialists ──► verify
                                                              ├─ respond ──► END
                                                              └─ summarize ──► escalate ──► END

    Returns:
        Compiled LangGraph workflow
    """
    workflow = StateGraph(OrchestratorState)

    # Add all nodes
    workflow.add_node("check_custom_answers", check_custom_answers_node)
    workflow.add_node("classify", classify_topic_node)
    workflow.add_node("route_specialists", route_to_specialists_node)
    workflow.add_node("verify", verify_response_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("respond", respond_node)
    workflow.add_node("escalate", escalate_node)

    # Entry point is the custom-answers gate
    workflow.set_entry_point("check_custom_answers")

    # custom_answers → respond (hit) or classify (miss)
    workflow.add_conditional_edges(
        "check_custom_answers",
        decide_after_custom_answers,
        {"respond": "respond", "classify": "classify"},
    )

    # Normal LLM path
    workflow.add_edge("classify", "route_specialists")
    workflow.add_edge("route_specialists", "verify")

    # After verification: respond directly, or summarise then escalate
    workflow.add_conditional_edges(
        "verify",
        decide_escalation,
        {"respond": "respond", "escalate": "summarize"},
    )
    workflow.add_edge("summarize", "escalate")

    # Terminal nodes
    workflow.add_edge("respond", END)
    workflow.add_edge("escalate", END)

    return workflow.compile()


# Create global orchestrator instance
orchestrator = create_orchestrator_graph()


async def run_aan_orchestrator(
    conversation_id: str,
    user_id: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Main entry point for the AAN orchestrator.

    Args:
        conversation_id: Caller-supplied or auto-generated conversation ID
        user_id: Opaque user identifier
        message: User message text
        context: Optional metadata dict (customer tier, order_id, channel, …)

    Returns:
        Dict with keys: status, message, confidence, sources, escalation_summary,
        agent, topic, resolution_state, custom_answer_used, handoff_summary
    """
    initial_state = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "message": message,
        "context": context or {},
        "classification": {},
        "specialist_responses": [],
        "verification": {},
        "final_response": "",
        "final_confidence": 0.0,
        "status": "pending",
        "escalation": {},
        "sources": [],
        "resolution_state": "in_progress",
        "custom_answer_id": "",
        "handoff_summary": "",
    }

    try:
        result = orchestrator.invoke(initial_state)

        # Prefer the AI handoff summary; fall back to escalator plain-text
        escalation_summary = result.get("handoff_summary") or result.get(
            "escalation", {}
        ).get("summary", "")

        return {
            "status": result.get("status", "error"),
            "message": result.get("final_response", ""),
            "confidence": result.get("final_confidence", 0.0),
            "sources": result.get("sources", []),
            "escalation_summary": escalation_summary,
            "agent": result.get("classification", {}).get("primary_topic", "unknown"),
            "topic": result.get("classification", {}).get("primary_topic", "unknown"),
            "resolution_state": result.get("resolution_state", "in_progress"),
            "custom_answer_used": bool(result.get("custom_answer_id")),
            "handoff_summary": result.get("handoff_summary", ""),
        }
    except Exception as e:
        print(f"Orchestrator error: {e}")
        return {
            "status": "error",
            "message": (
                "I apologize, but I'm having trouble processing your request. "
                "Let me connect you with a human agent who can help."
            ),
            "confidence": 0.0,
            "resolution_state": "in_progress",
            "custom_answer_used": False,
            "error": str(e),
        }
