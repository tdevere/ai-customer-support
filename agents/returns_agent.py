"""
Returns specialist agent implementation.
Handles order returns, refunds, and return policy questions.
"""

from typing import Dict, Any, List
from typing_extensions import TypedDict
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from integrations.tools.shopify_tools import shopify_tools
from shared.config import settings
from shared.rag import rag


class ReturnsAgentState(TypedDict):
    """State for returns agent."""

    messages: List
    order_id: str
    customer_email: str
    query: str
    response: str
    confidence: float
    sources: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]


def create_returns_agent():
    """
    Create the returns specialist agent subgraph.

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
    llm_with_tools = llm.bind_tools(shopify_tools)

    def analyze_query(state: ReturnsAgentState) -> ReturnsAgentState:
        """Analyze the returns query and retrieve return policy context."""
        query = state["query"]

        # Retrieve return policy and related information
        documents = rag.retrieve_context(query, topic="returns", top_k=3)
        context = rag.format_context_for_prompt(documents)

        state["sources"] = documents
        return state

    def execute_tools(state: ReturnsAgentState) -> ReturnsAgentState:
        """Execute Shopify tools to check orders and process returns."""
        query = state["query"]
        order_id = state.get("order_id")
        customer_email = state.get("customer_email")

        # Build a name→tool lookup for fast dispatch
        tool_map = {t.name: t for t in shopify_tools}

        system_prompt = """You are a returns specialist with access to Shopify order management.
Analyze the customer's return request and determine if you need to:
1. Look up order details
2. Check return eligibility
3. Process a refund

Available tools:
- get_order: Get order details by ID
- search_orders: Find orders by customer email
- check_return_eligibility: Check if an order is eligible for return
- create_refund: Process a refund

Always check eligibility before processing refunds. Be fair but follow the return policy strictly."""

        context_info = f"Customer query: {query}"
        if order_id:
            context_info += f"\nOrder ID: {order_id}"
        if customer_email:
            context_info += f"\nCustomer Email: {customer_email}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=context_info),
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

    def generate_response(state: ReturnsAgentState) -> ReturnsAgentState:
        """Generate final response about the return request."""
        query = state["query"]
        sources = state.get("sources", [])
        tool_results = state.get("tool_results", [])

        context = rag.format_context_for_prompt(sources)

        system_prompt = """You are a returns specialist for customer support.
Your job is to handle return and refund requests according to company policy.

Guidelines:
- Always reference our return policy
- Be empathetic but fair
- If you processed a refund or found the order ineligible, explain clearly
- Provide information about return shipping if applicable
- If you need more information, ask specific questions

At the end of your response, provide a confidence score (0.0 to 1.0).
Format: CONFIDENCE: 0.XX"""

        tool_context = ""
        if tool_results:
            tool_context = "\n\nOrder Information & Actions:\n" + "\n".join(
                [f"- {tr['tool']}: {tr.get('result', 'N/A')}" for tr in tool_results]
            )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"Return Policy:\n{context}\n{tool_context}\n\nCustomer Request: {query}"
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
    workflow = StateGraph(ReturnsAgentState)

    workflow.add_node("analyze", analyze_query)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("generate", generate_response)

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "execute_tools")
    workflow.add_edge("execute_tools", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile()


# Create and export agent
returns_agent = create_returns_agent()
