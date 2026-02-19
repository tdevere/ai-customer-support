"""
Escalator agent for human handoff.
"""

from typing import Dict, Any, List
from datetime import datetime


class EscalatorAgent:
    """
    Handles escalation to human agents with context preservation.
    """

    def escalate(
        self,
        conversation_id: str,
        query: str,
        attempted_responses: List[Dict[str, Any]],
        verification_result: Dict[str, Any],
        user_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Create escalation summary for human agent.

        Args:
            conversation_id: Conversation ID
            query: Original user query
            attempted_responses: Responses attempted by specialist agents
            verification_result: Verifier's assessment
            user_context: Additional user context

        Returns:
            Escalation summary and metadata
        """
        # Build escalation summary
        summary_parts = [
            "=" * 50,
            "ESCALATION SUMMARY",
            "=" * 50,
            f"Conversation ID: {conversation_id}",
            f"Time: {datetime.utcnow().isoformat()}",
            f"",
            f"Customer Query:",
            f"{query}",
            f"",
        ]

        # Add context if available
        if user_context:
            summary_parts.append("Customer Context:")
            for key, value in user_context.items():
                summary_parts.append(f"  - {key}: {value}")
            summary_parts.append("")

        # Add attempted responses
        if attempted_responses:
            summary_parts.append("Attempted Responses:")
            for i, resp in enumerate(attempted_responses, 1):
                agent = resp.get("agent", "Unknown")
                confidence = resp.get("confidence", 0)
                response = resp.get("response", "")
                summary_parts.append(
                    f"\n[Agent: {agent}, Confidence: {confidence:.2f}]"
                )
                summary_parts.append(
                    f"{response[:300]}..." if len(response) > 300 else response
                )
            summary_parts.append("")

        # Add verification notes
        verification = verification_result or {}
        summary_parts.extend(
            [
                "Verification Notes:",
                f"  - Grounded: {verification.get('grounded', 'N/A')}",
                f"  - Complete: {verification.get('complete', 'N/A')}",
                f"  - Final Confidence: {verification.get('final_confidence', 0):.2f}",
            ]
        )

        if verification.get("concerns"):
            summary_parts.append(f"  - Concerns: {', '.join(verification['concerns'])}")

        if verification.get("critique"):
            summary_parts.append(f"  - Critique: {verification['critique']}")

        summary_parts.extend(
            [
                "",
                "=" * 50,
                "ACTION REQUIRED: Please review and respond to customer",
                "=" * 50,
            ]
        )

        summary = "\n".join(summary_parts)

        # Determine escalation priority
        priority = self._determine_priority(verification_result)

        # Suggest tags
        tags = self._suggest_tags(query, attempted_responses, verification_result)

        return {
            "status": "escalated",
            "summary": summary,
            "priority": priority,
            "tags": tags,
            "conversation_id": conversation_id,
            "requires_human": True,
            "escalation_reason": verification.get(
                "critique", "Low confidence or unresolved issue"
            ),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _determine_priority(self, verification: Dict[str, Any]) -> str:
        """Determine escalation priority based on verification."""
        confidence = verification.get("final_confidence", 0)
        concerns = verification.get("concerns", [])

        if confidence < 0.3 or len(concerns) > 3:
            return "high"
        elif confidence < 0.5:
            return "medium"
        else:
            return "normal"

    def _suggest_tags(
        self,
        query: str,
        attempted_responses: List[Dict[str, Any]],
        verification: Dict[str, Any],
    ) -> List[str]:
        """Suggest tags for the escalated conversation."""
        tags = ["escalated", "needs_review"]

        # Add agent topics
        for resp in attempted_responses:
            agent = resp.get("agent", "")
            if agent:
                tags.append(f"attempted_{agent}")

        # Add verification flags
        if verification.get("grounded") == "no":
            tags.append("ungrounded")

        if verification.get("complete") == "no":
            tags.append("incomplete")

        # Add priority tag
        priority = self._determine_priority(verification)
        if priority != "normal":
            tags.append(f"priority_{priority}")

        return list(set(tags))  # Remove duplicates


# Global escalator instance
escalator = EscalatorAgent()
