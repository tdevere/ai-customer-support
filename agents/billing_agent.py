"""
Billing specialist agent implementation.
Handles billing, subscriptions, invoices, and payment issues.
"""

from typing import Dict, Any, List
from typing_extensions import TypedDict
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from integrations.tools.stripe_tools import stripe_tools
from shared.config import settings
from shared.rag import rag


class BillingAgentState(TypedDict):
    """State for billing agent."""

    messages: List
    customer_id: str
    query: str
    response: str
    confidence: float
    sources: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]


def create_billing_agent():
    """
    Create the billing specialist agent subgraph.

    Returns:
        Compiled LangGraph workflow
    """
    # Initialize LLM
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_gpt4,
        temperature=0.0,
    )

    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(stripe_tools)

    def analyze_query(state: BillingAgentState) -> BillingAgentState:
        """Analyze the billing query and retrieve relevant context."""
        query = state["query"]

        # Retrieve context from RAG
        documents = rag.retrieve_context(query, topic="billing", top_k=3)
        context = rag.format_context_for_prompt(documents)

        state["sources"] = documents
        return state

    def execute_tools(state: BillingAgentState) -> BillingAgentState:
        """Execute Stripe tools if needed."""
        query = state["query"]

        # Build a name→tool lookup for fast dispatch
        tool_map = {t.name: t for t in stripe_tools}

        system_prompt = """You are a billing specialist assistant with access to Stripe tools.
Analyze the customer query and determine if you need to call any Stripe tools to get information.
If you need tool calls, make them. Otherwise, proceed with answering based on available context.

Available tools:
- get_customer_info: Get customer details
- get_invoice: Get specific invoice details
- list_customer_invoices: List all customer invoices
- get_subscription: Get subscription details
- cancel_subscription: Cancel a subscription
- create_payment_intent: Create a payment intent

Be helpful, professional, and accurate. Only make tool calls if necessary."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"Customer query: {query}\n\nCustomer ID: {state.get('customer_id', 'unknown')}"
            ),
        ]

        response = llm_with_tools.invoke(messages)

        # Execute every tool the LLM requested
        tool_results = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("args", {})
                if tool_name in tool_map:
                    try:
                        result = tool_map[tool_name].invoke(tool_args)
                    except Exception as exc:
                        result = {"error": str(exc)}
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}
                tool_results.append(
                    {"tool": tool_name, "args": tool_args, "result": result}
                )

        state["tool_results"] = tool_results
        return state

    def generate_response(state: BillingAgentState) -> BillingAgentState:
        """Generate final response using context and tool results."""
        query = state["query"]
        sources = state.get("sources", [])
        tool_results = state.get("tool_results", [])

        context = rag.format_context_for_prompt(sources)

        system_prompt = """You are a billing specialist for customer support.
Your job is to answer billing-related questions accurately and professionally.

Use the provided context from our knowledge base and any tool results to answer the question.
Be concise but thorough. If you used tools to gather information, incorporate that data into your response.
If you cannot answer with confidence, say so clearly.

At the end of your response, provide a confidence score (0.0 to 1.0) indicating how confident you are in your answer.
Format: CONFIDENCE: 0.XX"""

        tool_context = ""
        if tool_results:
            tool_context = "\n\nTool Results:\n" + "\n".join(
                [f"- {tr['tool']}: {tr.get('result', 'N/A')}" for tr in tool_results]
            )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"Context:\n{context}\n{tool_context}\n\nCustomer Query: {query}"
            ),
        ]

        response = llm.invoke(messages)
        response_text = response.content

        # Extract confidence score
        confidence = 0.5
        if "CONFIDENCE:" in response_text:
            try:
                conf_str = response_text.split("CONFIDENCE:")[-1].strip().split()[0]
                confidence = float(conf_str)
                response_text = response_text.split("CONFIDENCE:")[0].strip()
            except:
                pass

        state["response"] = response_text
        state["confidence"] = confidence
        return state

    # Build graph
    workflow = StateGraph(BillingAgentState)

    workflow.add_node("analyze", analyze_query)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("generate", generate_response)

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "execute_tools")
    workflow.add_edge("execute_tools", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile()


# Create and export agent
billing_agent = create_billing_agent()
