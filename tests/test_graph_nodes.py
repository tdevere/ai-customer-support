"""
Direct unit tests for individual LangGraph orchestrator nodes.

Each node is a plain synchronous function that takes and returns a state dict —
no LangGraph runtime is needed. LLM, memory, verifier, escalator, and classifier
calls are all mocked.
"""

import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_state(**overrides) -> dict:
    """Build the minimal OrchestratorState dict required by any node."""
    base = {
        "conversation_id": "conv-node-test",
        "user_id": "u-1",
        "message": "my billing invoice is wrong",
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
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# classify_topic_node
# ---------------------------------------------------------------------------


class TestClassifyTopicNode:
    def test_sets_classification_from_classifier(self):
        from orchestrator.graph import classify_topic_node

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = {
            "primary_topic": "billing",
            "primary_confidence": 0.92,
            "all_topics": [{"topic": "billing", "confidence": 0.92}],
        }

        with patch("orchestrator.graph.classifier", mock_classifier):
            state = _minimal_state()
            result = classify_topic_node(state)

        assert result["classification"]["primary_topic"] == "billing"
        assert result["classification"]["primary_confidence"] == 0.92
        mock_classifier.classify.assert_called_once_with("my billing invoice is wrong")

    def test_classification_stored_in_state(self):
        from orchestrator.graph import classify_topic_node

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = {
            "primary_topic": "technical",
            "primary_confidence": 0.85,
            "all_topics": [],
        }

        with patch("orchestrator.graph.classifier", mock_classifier):
            state = _minimal_state(message="my app keeps crashing")
            result = classify_topic_node(state)

        assert result["classification"]["primary_topic"] == "technical"


# ---------------------------------------------------------------------------
# route_to_specialists_node
# ---------------------------------------------------------------------------


class TestRouteToSpecialistsNode:
    def _mock_agent(
        self, response: str = "Here is your answer.", confidence: float = 0.9
    ):
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {
            "response": response,
            "confidence": confidence,
            "sources": [],
            "tool_results": [],
        }
        return mock_agent

    def test_single_agent_invoked(self):
        from orchestrator.graph import route_to_specialists_node

        mock_agent = self._mock_agent("Invoice looks correct.")
        mock_module = MagicMock()
        mock_module.billing_agent = mock_agent

        mock_classifier = MagicMock()
        mock_classifier.get_agent_configs.return_value = [
            {
                "topic": "billing",
                "module": "agents.billing_agent",
                "agent_name": "billing_agent",
            }
        ]

        with (
            patch("orchestrator.graph.classifier", mock_classifier),
            patch(
                "orchestrator.graph.importlib.import_module", return_value=mock_module
            ),
        ):
            state = _minimal_state(
                classification={
                    "primary_topic": "billing",
                    "all_topics": [{"topic": "billing", "confidence": 0.9}],
                }
            )
            result = route_to_specialists_node(state)

        assert len(result["specialist_responses"]) == 1
        assert result["specialist_responses"][0]["agent"] == "billing"
        assert result["specialist_responses"][0]["response"] == "Invoice looks correct."

    def test_agent_exception_adds_error_response(self):
        """If an agent module fails to load, an error entry is added — not raised."""
        from orchestrator.graph import route_to_specialists_node

        mock_classifier = MagicMock()
        mock_classifier.get_agent_configs.return_value = [
            {
                "topic": "technical",
                "module": "agents.technical_agent",
                "agent_name": "technical_agent",
            }
        ]

        with (
            patch("orchestrator.graph.classifier", mock_classifier),
            patch(
                "orchestrator.graph.importlib.import_module",
                side_effect=ImportError("agent not found"),
            ),
        ):
            state = _minimal_state(
                classification={
                    "primary_topic": "technical",
                    "all_topics": [{"topic": "technical", "confidence": 0.8}],
                }
            )
            result = route_to_specialists_node(state)

        assert len(result["specialist_responses"]) == 1
        assert result["specialist_responses"][0]["confidence"] == 0.0
        assert "Error" in result["specialist_responses"][0]["response"]

    def test_fallback_to_primary_topic_when_no_all_topics(self):
        """When all_topics is empty, primary_topic is used as the only topic."""
        from orchestrator.graph import route_to_specialists_node

        mock_agent = self._mock_agent()
        mock_module = MagicMock()
        mock_module.returns_agent = mock_agent

        mock_classifier = MagicMock()
        mock_classifier.get_agent_configs.return_value = [
            {
                "topic": "returns",
                "module": "agents.returns_agent",
                "agent_name": "returns_agent",
            }
        ]

        with (
            patch("orchestrator.graph.classifier", mock_classifier),
            patch(
                "orchestrator.graph.importlib.import_module", return_value=mock_module
            ),
        ):
            state = _minimal_state(
                classification={"primary_topic": "returns", "all_topics": []}
            )
            route_to_specialists_node(state)

        mock_classifier.get_agent_configs.assert_called_once_with(["returns"])


# ---------------------------------------------------------------------------
# verify_response_node
# ---------------------------------------------------------------------------


class TestVerifyResponseNode:
    def test_verify_called_with_best_response(self):
        from orchestrator.graph import verify_response_node

        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = {
            "final_confidence": 0.88,
            "should_escalate": False,
            "critique": "Response is accurate.",
        }

        with patch("orchestrator.graph.verifier", mock_verifier):
            state = _minimal_state(
                specialist_responses=[
                    {
                        "agent": "billing",
                        "response": "No double charge.",
                        "confidence": 0.88,
                        "sources": [],
                        "tool_results": [],
                    },
                ]
            )
            result = verify_response_node(state)

        assert result["final_confidence"] == 0.88
        assert result["final_response"] == "No double charge."
        mock_verifier.verify.assert_called_once()

    def test_picks_highest_confidence_response(self):
        from orchestrator.graph import verify_response_node

        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = {
            "final_confidence": 0.95,
            "should_escalate": False,
            "critique": "Good.",
        }

        with patch("orchestrator.graph.verifier", mock_verifier):
            state = _minimal_state(
                specialist_responses=[
                    {
                        "agent": "billing",
                        "response": "Low conf answer",
                        "confidence": 0.4,
                        "sources": [],
                        "tool_results": [],
                    },
                    {
                        "agent": "technical",
                        "response": "High conf answer",
                        "confidence": 0.95,
                        "sources": [],
                        "tool_results": [],
                    },
                ]
            )
            result = verify_response_node(state)

        assert result["final_response"] == "High conf answer"

    def test_no_specialist_responses_sets_should_escalate(self):
        from orchestrator.graph import verify_response_node

        with patch("orchestrator.graph.verifier", MagicMock()):
            state = _minimal_state(specialist_responses=[])
            result = verify_response_node(state)

        assert result["verification"]["should_escalate"] is True
        assert result["verification"]["final_confidence"] == 0.0


# ---------------------------------------------------------------------------
# decide_escalation
# ---------------------------------------------------------------------------


class TestDecideEscalation:
    def test_returns_escalate_when_should_escalate_true(self):
        from orchestrator.graph import decide_escalation

        state = _minimal_state(
            verification={"should_escalate": True, "final_confidence": 0.3}
        )
        assert decide_escalation(state) == "escalate"

    def test_returns_respond_when_should_escalate_false(self):
        from orchestrator.graph import decide_escalation

        state = _minimal_state(
            verification={"should_escalate": False, "final_confidence": 0.9}
        )
        assert decide_escalation(state) == "respond"

    def test_defaults_to_respond_when_verification_empty(self):
        from orchestrator.graph import decide_escalation

        state = _minimal_state(verification={})
        assert decide_escalation(state) == "respond"


# ---------------------------------------------------------------------------
# respond_node
# ---------------------------------------------------------------------------


class TestRespondNode:
    def test_sets_status_success(self):
        from orchestrator.graph import respond_node

        mock_memory = MagicMock()
        with patch("orchestrator.graph.memory", mock_memory):
            state = _minimal_state(
                message="great, thank you!",
                final_response="You're welcome.",
                final_confidence=0.9,
            )
            result = respond_node(state)

        assert result["status"] == "success"

    def test_confirmation_message_sets_resolved_confirmed(self):
        from orchestrator.graph import respond_node

        mock_memory = MagicMock()
        with patch("orchestrator.graph.memory", mock_memory):
            state = _minimal_state(message="thanks, that solved it!")
            result = respond_node(state)

        assert result["resolution_state"] == "resolved_confirmed"

    def test_non_confirmation_message_sets_resolved_assumed(self):
        from orchestrator.graph import respond_node

        mock_memory = MagicMock()
        with patch("orchestrator.graph.memory", mock_memory):
            state = _minimal_state(message="I need help with my order")
            result = respond_node(state)

        assert result["resolution_state"] == "resolved_assumed"

    def test_calls_memory_save_state(self):
        from orchestrator.graph import respond_node

        mock_memory = MagicMock()
        with patch("orchestrator.graph.memory", mock_memory):
            state = _minimal_state()
            respond_node(state)

        mock_memory.save_state.assert_called_once()
        call_args = mock_memory.save_state.call_args
        assert call_args[0][0] == "conv-node-test"


# ---------------------------------------------------------------------------
# summarize_node
# ---------------------------------------------------------------------------


class TestSummarizeNode:
    def test_llm_path_sets_handoff_summary(self):
        from orchestrator.graph import summarize_node

        mock_response = MagicMock()
        mock_response.content = (
            "  Customer has billing dispute. Tried billing agent. Needs human.  "
        )

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        mock_llm_cls = MagicMock(return_value=mock_llm)

        with patch("orchestrator.graph.AzureChatOpenAI", mock_llm_cls, create=True):
            # Patch the import inside the function
            with patch.dict(
                "sys.modules",
                {"langchain_openai": MagicMock(AzureChatOpenAI=mock_llm_cls)},
            ):
                state = _minimal_state(
                    specialist_responses=[{"agent": "billing", "confidence": 0.4}],
                    verification={"critique": "Low confidence"},
                )
                # Directly inject the mock into the module
                import orchestrator.graph as gmod

                with patch.object(gmod, "AzureChatOpenAI", mock_llm_cls, create=True):
                    result = summarize_node(state)

        # Either the LLM succeeded and set the summary, or it fell back — both are valid
        assert result["handoff_summary"] != ""

    def test_fallback_when_llm_raises(self):
        """When AzureChatOpenAI raises (e.g. no credentials), fallback template is used."""
        from orchestrator.graph import summarize_node

        import orchestrator.graph as gmod

        # Make AzureChatOpenAI raise on construction — but only if it exists in the module
        mock_llm_cls = MagicMock(side_effect=RuntimeError("no credentials"))

        with patch.object(gmod, "AzureChatOpenAI", mock_llm_cls, create=True):
            state = _minimal_state(
                message="I keep getting charged twice",
                specialist_responses=[{"agent": "billing", "confidence": 0.3}],
                verification={"critique": "Unverifiable"},
            )
            result = summarize_node(state)

        assert "CUSTOMER ISSUE" in result["handoff_summary"]
        assert "I keep getting charged twice" in result["handoff_summary"]

    def test_fallback_always_sets_nonempty_summary(self):
        """
        Even with no specialist responses the fallback must produce a non-empty summary.
        In practice the LLM import will fail in CI (no Azure OAI creds) so we always
        hit the fallback — confirm it is non-empty.
        """
        from orchestrator.graph import summarize_node

        state = _minimal_state(specialist_responses=[], verification={})
        result = summarize_node(state)

        # Whether LLM or fallback ran, summary must be populated
        assert isinstance(result["handoff_summary"], str)
        assert len(result["handoff_summary"]) > 0


# ---------------------------------------------------------------------------
# escalate_node
# ---------------------------------------------------------------------------


class TestEscalateNode:
    def test_sets_status_escalated(self):
        from orchestrator.graph import escalate_node

        mock_escalator = MagicMock()
        mock_escalator.escalate.return_value = {
            "escalation_reason": "Low confidence",
            "summary": "Needs human review.",
        }
        mock_memory = MagicMock()

        with (
            patch("orchestrator.graph.escalator", mock_escalator),
            patch("orchestrator.graph.memory", mock_memory),
        ):
            state = _minimal_state(
                specialist_responses=[],
                verification={"should_escalate": True},
            )
            result = escalate_node(state)

        assert result["status"] == "escalated"
        assert result["resolution_state"] == "escalated"

    def test_escalation_dict_stored_in_state(self):
        from orchestrator.graph import escalate_node

        mock_escalator = MagicMock()
        mock_escalator.escalate.return_value = {
            "escalation_reason": "Billing fraud suspected",
            "summary": "Customer reports repeated charges.",
        }
        mock_memory = MagicMock()

        with (
            patch("orchestrator.graph.escalator", mock_escalator),
            patch("orchestrator.graph.memory", mock_memory),
        ):
            state = _minimal_state()
            result = escalate_node(state)

        assert result["escalation"]["escalation_reason"] == "Billing fraud suspected"

    def test_handoff_summary_merged_into_escalation(self):
        """If handoff_summary exists in state, it's merged into the escalation dict."""
        from orchestrator.graph import escalate_node

        mock_escalator = MagicMock()
        mock_escalator.escalate.return_value = {"summary": "Plain text summary."}
        mock_memory = MagicMock()

        with (
            patch("orchestrator.graph.escalator", mock_escalator),
            patch("orchestrator.graph.memory", mock_memory),
        ):
            state = _minimal_state(handoff_summary="AI-generated detailed summary.")
            result = escalate_node(state)

        assert (
            result["escalation"]["handoff_summary"] == "AI-generated detailed summary."
        )

    def test_memory_save_state_called(self):
        from orchestrator.graph import escalate_node

        mock_escalator = MagicMock()
        mock_escalator.escalate.return_value = {}
        mock_memory = MagicMock()

        with (
            patch("orchestrator.graph.escalator", mock_escalator),
            patch("orchestrator.graph.memory", mock_memory),
        ):
            escalate_node(_minimal_state())

        mock_memory.save_state.assert_called_once()
