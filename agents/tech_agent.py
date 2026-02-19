"""
Tech support specialist agent implementation.
Handles technical issues, documentation, and Jira ticket creation.
"""

from typing import Dict, Any, List
from typing_extensions import TypedDict
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from integrations.tools.jira_tools import jira_tools
from shared.config import settings
from shared.rag import rag


class TechAgentState(TypedDict):
    """State for tech support agent."""

    messages: List
    user_id: str
    query: str
    response: str
    confidence: float
    sources: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    jira_ticket: Dict[str, Any]


def create_tech_agent():
    """
    Create the tech support specialist agent subgraph.

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
    llm_with_tools = llm.bind_tools(jira_tools)

    def analyze_query(state: TechAgentState) -> TechAgentState:
        """Analyze the technical query and retrieve relevant documentation."""
        query = state["query"]

        # Retrieve context from technical documentation
        documents = rag.retrieve_context(query, topic="technical", top_k=5)
        context = rag.format_context_for_prompt(documents)

        state["sources"] = documents
        return state

    def execute_tools(state: TechAgentState) -> TechAgentState:
        """Execute Jira tools if needed (search tickets, create ticket)."""
        query = state["query"]

        system_prompt = """You are a technical support specialist with access to Jira.
Analyze the customer's technical issue and determine if you need to:
1. Search for existing Jira tickets about similar issues
2. Create a new Jira ticket if this is a new bug or issue that needs engineering attention

Available tools:
- search_jira_tickets: Search for existing tickets
- get_jira_ticket: Get details of a specific ticket
- create_jira_ticket: Create a new ticket for the engineering team

Be thorough and professional. Only create tickets for genuine technical issues that require engineering attention."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"Customer's technical issue: {query}\n\nUser ID: {state.get('user_id', 'unknown')}"
            ),
        ]

        response = llm_with_tools.invoke(messages)

        # Store tool results if any
        tool_results = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_results.append(
                    {
                        "tool": tool_call.get("name"),
                        "args": tool_call.get("args"),
                        "result": "Tool execution placeholder",
                    }
                )

        state["tool_results"] = tool_results
        return state

    def generate_response(state: TechAgentState) -> TechAgentState:
        """Generate final response with technical solution."""
        query = state["query"]
        sources = state.get("sources", [])
        tool_results = state.get("tool_results", [])

        context = rag.format_context_for_prompt(sources)

        system_prompt = """You are a technical support specialist.
Your job is to help customers resolve technical issues using our documentation and knowledge base.

Guidelines:
- Provide clear, step-by-step solutions when possible
- Reference documentation sources
- If you created or found a Jira ticket, mention it
- Be empathetic to technical frustrations
- If the issue cannot be resolved immediately, explain next steps clearly

At the end of your response, provide a confidence score (0.0 to 1.0).
Format: CONFIDENCE: 0.XX"""

        tool_context = ""
        if tool_results:
            tool_context = "\n\nActions Taken:\n" + "\n".join(
                [f"- {tr['tool']}: {tr.get('result', 'N/A')}" for tr in tool_results]
            )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"Documentation:\n{context}\n{tool_context}\n\nCustomer Issue: {query}"
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
    workflow = StateGraph(TechAgentState)

    workflow.add_node("analyze", analyze_query)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("generate", generate_response)

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "execute_tools")
    workflow.add_edge("execute_tools", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile()


# Create and export agent
tech_agent = create_tech_agent()
