"""
Main LangGraph orchestrator for the AAN system.
Coordinates topic classification, specialist routing, verification, and escalation.
"""

import importlib
from typing import Dict, Any, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from orchestrator.supervisor import classifier
from orchestrator.verifier import verifier
from orchestrator.escalator import escalator
from shared.memory import memory
from shared.config import settings


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
    Prepare successful response for Intercom.
    """
    state["status"] = "success"

    # Save state to memory
    memory.save_state(
        state["conversation_id"],
        {
            "message": state["message"],
            "response": state["final_response"],
            "confidence": state["final_confidence"],
            "classification": state["classification"],
            "timestamp": "now",
        },
    )

    print(f"Responding with confidence {state['final_confidence']}")

    return state


def escalate_node(state: OrchestratorState) -> OrchestratorState:
    """
    Escalate to human agent.
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

    # Save state to memory
    memory.save_state(
        state["conversation_id"],
        {
            "message": state["message"],
            "escalation": escalation,
            "classification": state["classification"],
            "timestamp": "now",
        },
    )

    print(f"Escalated: {escalation.get('escalation_reason', 'Unknown reason')}")

    return state


def create_orchestrator_graph():
    """
    Create the main orchestrator graph.

    Returns:
        Compiled LangGraph workflow
    """
    workflow = StateGraph(OrchestratorState)

    # Add nodes
    workflow.add_node("classify", classify_topic_node)
    workflow.add_node("route_specialists", route_to_specialists_node)
    workflow.add_node("verify", verify_response_node)
    workflow.add_node("respond", respond_node)
    workflow.add_node("escalate", escalate_node)

    # Build graph flow
    workflow.set_entry_point("classify")
    workflow.add_edge("classify", "route_specialists")
    workflow.add_edge("route_specialists", "verify")

    # Conditional edge based on verification
    workflow.add_conditional_edges(
        "verify", decide_escalation, {"respond": "respond", "escalate": "escalate"}
    )

    # End nodes
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
    Main entry point for running the AAN orchestrator.

    Args:
        conversation_id: Intercom conversation ID
        user_id: User/customer ID
        message: User message
        context: Additional context from Intercom

    Returns:
        Orchestrator result with response or escalation
    """
    # Prepare initial state
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
    }

    # Run orchestrator
    try:
        result = orchestrator.invoke(initial_state)

        return {
            "status": result.get("status", "error"),
            "message": result.get("final_response", ""),
            "confidence": result.get("final_confidence", 0.0),
            "sources": result.get("sources", []),
            "escalation_summary": result.get("escalation", {}).get("summary", ""),
            "agent": result.get("classification", {}).get("primary_topic", "unknown"),
            "topic": result.get("classification", {}).get("primary_topic", "unknown"),
        }
    except Exception as e:
        print(f"Orchestrator error: {e}")
        return {
            "status": "error",
            "message": "I apologize, but I'm having trouble processing your request. Let me connect you with a human agent who can help.",
            "confidence": 0.0,
            "error": str(e),
        }
