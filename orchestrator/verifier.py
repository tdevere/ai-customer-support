"""
Verifier agent for confidence scoring and fact-checking.
"""

from typing import Dict, Any, List
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from shared.config import settings


class VerifierAgent:
    """
    Verifies specialist agent responses for accuracy and confidence.
    Performs grounding checks and self-critique.
    """

    def __init__(self):
        """Initialize verifier with LLM."""
        self.llm = AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            deployment_name=settings.azure_openai_deployment_gpt4,
            temperature=0.0,
        )

    def verify(
        self,
        query: str,
        response: str,
        sources: List[Dict[str, Any]],
        agent_confidence: float,
        tool_results: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Verify agent response and compute final confidence score.

        Args:
            query: Original user query
            response: Agent's response
            sources: RAG sources used
            agent_confidence: Agent's self-reported confidence
            tool_results: Results from any tools used

        Returns:
            Verification result with final confidence and critique
        """
        # Build context for verification
        sources_text = self._format_sources(sources)
        tools_text = (
            self._format_tools(tool_results) if tool_results else "No tools used"
        )

        system_prompt = """You are a verification agent that checks responses for accuracy and completeness.
Your job is to:
1. Check if the response is grounded in the provided sources
2. Identify any potential hallucinations or unsupported claims
3. Assess if the response fully addresses the user's query
4. Consider tool results and ensure they're properly incorporated
5. Compute a final confidence score

Scoring guidelines:
- 0.9-1.0: Fully grounded, complete answer with strong supporting evidence
- 0.7-0.89: Good answer with minor gaps or slight uncertainty
- 0.5-0.69: Partial answer or moderate uncertainty
- 0.3-0.49: Significant gaps or low confidence
- 0.0-0.29: Unsupported or likely incorrect

Provide your assessment in this format:
GROUNDED: yes/no/partial
COMPLETE: yes/no/partial
CONCERNS: list any issues
FINAL_CONFIDENCE: 0.XX
CRITIQUE: brief explanation"""

        user_message = f"""User Query: {query}

Agent Response: {response}

Sources Used:
{sources_text}

Tool Results:
{tools_text}

Agent's Self-Reported Confidence: {agent_confidence}

Verify this response and provide your assessment."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]

        verification = self.llm.invoke(messages)
        result = self._parse_verification(verification.content, agent_confidence)

        return result

    def _format_sources(self, sources: List[Dict[str, Any]]) -> str:
        """Format RAG sources for verification."""
        if not sources:
            return "No sources provided"

        formatted = []
        for i, source in enumerate(sources, 1):
            formatted.append(
                f"[{i}] {source.get('title', 'Untitled')}: {source.get('content', '')[:200]}..."
            )
        return "\n".join(formatted)

    def _format_tools(self, tool_results: List[Dict[str, Any]]) -> str:
        """Format tool results for verification."""
        if not tool_results:
            return "No tools used"

        formatted = []
        for tool in tool_results:
            formatted.append(
                f"- {tool.get('tool', 'Unknown')}: {tool.get('result', 'N/A')}"
            )
        return "\n".join(formatted)

    def _parse_verification(
        self, verification_text: str, agent_confidence: float
    ) -> Dict[str, Any]:
        """Parse verifier response."""
        result = {
            "grounded": "partial",
            "complete": "partial",
            "concerns": [],
            "final_confidence": agent_confidence,  # Default to agent's confidence
            "critique": "",
            "should_escalate": False,
        }

        lines = verification_text.strip().split("\n")

        for line in lines:
            line = line.strip()

            if line.startswith("GROUNDED:"):
                result["grounded"] = line.split(":", 1)[1].strip().lower()

            elif line.startswith("COMPLETE:"):
                result["complete"] = line.split(":", 1)[1].strip().lower()

            elif line.startswith("CONCERNS:"):
                concerns = line.split(":", 1)[1].strip()
                if concerns and concerns.lower() not in ["none", "n/a"]:
                    result["concerns"] = [c.strip() for c in concerns.split(",")]

            elif line.startswith("FINAL_CONFIDENCE:"):
                try:
                    conf = float(line.split(":", 1)[1].strip())
                    result["final_confidence"] = conf
                except:
                    pass

            elif line.startswith("CRITIQUE:"):
                result["critique"] = line.split(":", 1)[1].strip()

        # Determine if should escalate
        result["should_escalate"] = (
            result["final_confidence"] < settings.confidence_threshold
            or result["grounded"] == "no"
            or len(result["concerns"]) > 2
        )

        return result


# Global verifier instance
verifier = VerifierAgent()
