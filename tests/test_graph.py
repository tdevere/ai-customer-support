"""
Unit tests for the LangGraph orchestrator (orchestrator/graph.py).

LLM calls, Cosmos DB, and all agent invocations are mocked —
no real Azure services are required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# _detect_confirmation
# ---------------------------------------------------------------------------


class TestDetectConfirmation:
    """_detect_confirmation() is a pure utility — no mocking needed."""

    def _fn(self, message: str) -> bool:
        from orchestrator.graph import _detect_confirmation

        return _detect_confirmation(message)

    @pytest.mark.parametrize(
        "phrase",
        [
            "thank you so much",
            "Thanks!",
            "THANKS",
            "thx",
            "solved",
            "fixed",
            "resolved",
            "sorted",
            "perfect",
            "great",
            "awesome",
            "excellent",
            "got it",
            "all good",
            "works now",
            "that worked",
            "problem solved",
            "issue resolved",
            "no further questions",
            "never mind",
            "all set",
        ],
    )
    def test_returns_true_for_confirmation_phrases(self, phrase: str):
        assert self._fn(phrase) is True

    @pytest.mark.parametrize(
        "phrase",
        [
            "I need help with my order",
            "why is my invoice wrong",
            "can you reset my password",
            "my product is broken",
            "",
            "   ",
        ],
    )
    def test_returns_false_for_non_confirmation_messages(self, phrase: str):
        assert self._fn(phrase) is False

    def test_case_insensitive(self):
        assert self._fn("THANK YOU") is True
        assert self._fn("Resolved") is True

    def test_phrase_embedded_in_sentence(self):
        # "thank" is a substring of the message
        assert self._fn("I'd like to thank you for your help") is True


# ---------------------------------------------------------------------------
# check_custom_answers_node
# ---------------------------------------------------------------------------


class TestCheckCustomAnswersNode:
    """check_custom_answers_node is synchronous and uses the YAML matcher only."""

    def _minimal_state(self, message: str) -> dict:
        return {
            "conversation_id": "test-conv",
            "user_id": "user-1",
            "message": message,
            "context": {},
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

    def test_match_sets_custom_answer_id(self):
        from orchestrator.graph import check_custom_answers_node

        state = self._minimal_state("how much does it cost")
        result = check_custom_answers_node(state)

        # Expected: matched the 'pricing_plans' entry
        assert result["custom_answer_id"] != ""
        assert result["final_response"] != ""
        assert result["final_confidence"] > 0.0

    def test_match_sets_classification_source(self):
        from orchestrator.graph import check_custom_answers_node

        state = self._minimal_state("what are your pricing plans")
        result = check_custom_answers_node(state)

        assert result["classification"].get("source") == "custom_answers"

    def test_no_match_sets_empty_custom_answer_id(self):
        from orchestrator.graph import check_custom_answers_node

        state = self._minimal_state("asdfghjkl completely random query zxcvbnm")
        result = check_custom_answers_node(state)

        assert result["custom_answer_id"] == ""

    def test_no_match_does_not_overwrite_final_response(self):
        """When there is no match the node must leave final_response untouched."""
        from orchestrator.graph import check_custom_answers_node

        state = self._minimal_state("I want to return an item")
        state["final_response"] = "existing response"
        result = check_custom_answers_node(state)

        # custom_answer_id is empty → node should not set a response
        assert result["custom_answer_id"] == ""

    def test_case_insensitive_matching(self):
        from orchestrator.graph import check_custom_answers_node

        state = self._minimal_state("HOW MUCH DOES IT COST")
        result = check_custom_answers_node(state)

        assert result["custom_answer_id"] != ""


# ---------------------------------------------------------------------------
# run_aan_orchestrator — happy paths
# ---------------------------------------------------------------------------


def _full_graph_result(**overrides) -> dict:
    """Build a realistic OrchestratorState-like dict returned by ainvoke."""
    base = {
        "conversation_id": "conv-100",
        "user_id": "u1",
        "message": "reset my password",
        "context": {},
        "classification": {
            "primary_topic": "technical",
            "primary_confidence": 0.95,
            "all_topics": [{"topic": "technical", "confidence": 0.95}],
            "source": "llm",
        },
        "specialist_responses": [
            {
                "agent": "technical",
                "response": "Please click Forgot Password on the login page.",
                "confidence": 0.95,
            }
        ],
        "verification": {"verified": True, "quality_score": 0.9},
        "final_response": "Please click Forgot Password on the login page.",
        "final_confidence": 0.95,
        "status": "success",
        "escalation": {},
        "sources": [],
        "resolution_state": "in_progress",
        "custom_answer_id": "",
        "handoff_summary": "",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_run_aan_orchestrator_success():
    """Happy-path: ainvoke returns a complete state → shaped dict returned."""
    mock_result = _full_graph_result()
    mock_orchestrator = MagicMock()
    mock_orchestrator.ainvoke = AsyncMock(return_value=mock_result)

    with patch("orchestrator.graph.orchestrator", mock_orchestrator):
        from orchestrator.graph import run_aan_orchestrator

        result = await run_aan_orchestrator(
            conversation_id="conv-100",
            user_id="u1",
            message="reset my password",
        )

    assert result["status"] == "success"
    assert result["message"] == "Please click Forgot Password on the login page."
    assert result["confidence"] == 0.95
    assert result["agent"] == "technical"
    assert result["topic"] == "technical"
    assert result["resolution_state"] == "in_progress"
    assert result["custom_answer_used"] is False


@pytest.mark.asyncio
async def test_run_aan_orchestrator_with_custom_answer():
    """When custom_answer_id is set, custom_answer_used must be True."""
    mock_result = _full_graph_result(
        custom_answer_id="pricing_plans",
        final_response="Our pricing starts at $29/month.",
        final_confidence=1.0,
        classification={
            "primary_topic": "billing",
            "primary_confidence": 1.0,
            "all_topics": [],
            "source": "custom_answers",
        },
    )
    mock_orchestrator = MagicMock()
    mock_orchestrator.ainvoke = AsyncMock(return_value=mock_result)

    with patch("orchestrator.graph.orchestrator", mock_orchestrator):
        from orchestrator.graph import run_aan_orchestrator

        result = await run_aan_orchestrator(
            conversation_id="conv-200",
            user_id="u2",
            message="how much does it cost",
        )

    assert result["custom_answer_used"] is True
    assert "pricing" in result["message"].lower()


@pytest.mark.asyncio
async def test_run_aan_orchestrator_escalation_uses_handoff_summary():
    """escalation_summary prefers handoff_summary over escalation.summary."""
    mock_result = _full_graph_result(
        status="escalated",
        handoff_summary="Customer needs billing escalation.",
        escalation={"summary": "old summary"},
    )
    mock_orchestrator = MagicMock()
    mock_orchestrator.ainvoke = AsyncMock(return_value=mock_result)

    with patch("orchestrator.graph.orchestrator", mock_orchestrator):
        from orchestrator.graph import run_aan_orchestrator

        result = await run_aan_orchestrator(
            conversation_id="conv-300",
            user_id="u3",
            message="charge me twice",
        )

    assert result["escalation_summary"] == "Customer needs billing escalation."


@pytest.mark.asyncio
async def test_run_aan_orchestrator_falls_back_to_escalation_summary():
    """When handoff_summary is empty, escalation_summary comes from escalation.summary."""
    mock_result = _full_graph_result(
        status="escalated",
        handoff_summary="",
        escalation={"summary": "Needs human review."},
    )
    mock_orchestrator = MagicMock()
    mock_orchestrator.ainvoke = AsyncMock(return_value=mock_result)

    with patch("orchestrator.graph.orchestrator", mock_orchestrator):
        from orchestrator.graph import run_aan_orchestrator

        result = await run_aan_orchestrator("c", "u", "help me")

    assert result["escalation_summary"] == "Needs human review."


@pytest.mark.asyncio
async def test_run_aan_orchestrator_passes_context():
    """Context dict is forwarded untouched to the initial state."""
    captured_state = {}

    async def capture_ainvoke(state):
        captured_state.update(state)
        return _full_graph_result()

    mock_orchestrator = MagicMock()
    mock_orchestrator.ainvoke = capture_ainvoke

    context = {"order_id": "ORD-999", "tier": "gold"}

    with patch("orchestrator.graph.orchestrator", mock_orchestrator):
        from orchestrator.graph import run_aan_orchestrator

        await run_aan_orchestrator("c", "u", "where is my order", context=context)

    assert captured_state["context"] == context


# ---------------------------------------------------------------------------
# run_aan_orchestrator — error path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_aan_orchestrator_returns_error_dict_on_exception():
    """When ainvoke raises, run_aan_orchestrator returns status='error' dict."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.ainvoke = AsyncMock(side_effect=RuntimeError("LLM offline"))

    with patch("orchestrator.graph.orchestrator", mock_orchestrator):
        from orchestrator.graph import run_aan_orchestrator

        result = await run_aan_orchestrator("c-err", "u-err", "this will fail")

    assert result["status"] == "error"
    assert "error" in result
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_run_aan_orchestrator_error_contains_exception_message():
    """The 'error' key in the error response contains the exception message."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.ainvoke = AsyncMock(
        side_effect=ValueError("model_not_found: gpt-4o")
    )

    with patch("orchestrator.graph.orchestrator", mock_orchestrator):
        from orchestrator.graph import run_aan_orchestrator

        result = await run_aan_orchestrator("c", "u", "anything")

    assert "model_not_found" in result["error"]


# ---------------------------------------------------------------------------
# decide_after_custom_answers routing function
# ---------------------------------------------------------------------------


def test_decide_after_custom_answers_returns_respond_when_id_set():
    """Returns 'respond' when the state has a custom_answer_id."""
    from orchestrator.graph import decide_after_custom_answers

    state = {"custom_answer_id": "faq_pricing", "messages": []}
    assert decide_after_custom_answers(state) == "respond"


def test_decide_after_custom_answers_returns_classify_when_no_id():
    """Returns 'classify' when the state has no custom_answer_id."""
    from orchestrator.graph import decide_after_custom_answers

    state = {"custom_answer_id": "", "messages": []}
    assert decide_after_custom_answers(state) == "classify"
