"""
Unit tests for the custom-answers override layer.
"""

import pytest
from orchestrator.custom_answers import CustomAnswersMatcher


@pytest.fixture
def matcher():
    """Create a fresh matcher using the real custom_answers.yaml."""
    return CustomAnswersMatcher()


# ---------------------------------------------------------------------------
# Basic matching
# ---------------------------------------------------------------------------


def test_matcher_loads_entries(matcher):
    """Matcher should load at least one entry from the YAML file."""
    assert matcher.entry_count > 0


def test_pricing_match(matcher):
    result = matcher.match("How much does it cost per month?")
    assert result is not None
    assert result["topic"] == "billing"
    assert result["confidence"] >= 0.95
    assert len(result["answer"]) > 10


def test_pricing_match_case_insensitive(matcher):
    result = matcher.match("HOW MUCH DOES IT COST")
    assert result is not None
    assert result["topic"] == "billing"


def test_refund_match(matcher):
    result = matcher.match("What is your refund policy?")
    assert result is not None
    assert result["id"] == "refund_policy"


def test_support_hours_match(matcher):
    result = matcher.match("What are your support hours?")
    assert result is not None
    assert result["id"] == "support_hours"
    assert result["topic"] == "general"


def test_system_status_match(matcher):
    result = matcher.match("Is the system down right now?")
    assert result is not None
    assert result["id"] == "system_status"


def test_api_docs_match(matcher):
    result = matcher.match("Where can I find your API documentation?")
    assert result is not None
    assert result["topic"] == "technical"


def test_no_match_returns_none(matcher):
    """Unrelated message should not match any custom answer."""
    result = matcher.match("Why is my order taking so long to ship?")
    assert result is None


def test_empty_message_returns_none(matcher):
    result = matcher.match("")
    assert result is None


# ---------------------------------------------------------------------------
# Match result structure
# ---------------------------------------------------------------------------


def test_match_result_has_required_keys(matcher):
    result = matcher.match("What are your pricing plans?")
    assert result is not None
    for key in ("id", "topic", "answer", "confidence"):
        assert key in result, f"Missing key: {key}"


def test_match_confidence_in_range(matcher):
    result = matcher.match("What are your support hours?")
    assert result is not None
    assert 0.0 < result["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Disabled entries (inject a custom YAML)
# ---------------------------------------------------------------------------


def test_disabled_entry_not_matched(tmp_path):
    yaml_content = """
custom_answers:
  - id: "test_disabled"
    topic: "general"
    enabled: false
    confidence: 0.99
    patterns:
      - "hello world"
    answer: "You should not see this."
"""
    yaml_file = tmp_path / "custom_answers.yaml"
    yaml_file.write_text(yaml_content)

    m = CustomAnswersMatcher(str(yaml_file))
    assert m.match("hello world") is None


def test_enabled_entry_matched(tmp_path):
    yaml_content = """
custom_answers:
  - id: "test_enabled"
    topic: "general"
    enabled: true
    confidence: 0.99
    patterns:
      - "hello world"
    answer: "Hello back!"
"""
    yaml_file = tmp_path / "custom_answers.yaml"
    yaml_file.write_text(yaml_content)

    m = CustomAnswersMatcher(str(yaml_file))
    result = m.match("say hello world please")
    assert result is not None
    assert result["id"] == "test_enabled"
    assert result["answer"] == "Hello back!"


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_missing_yaml_returns_empty(tmp_path):
    """Matcher should not raise if the YAML file doesn't exist."""
    m = CustomAnswersMatcher(str(tmp_path / "nonexistent.yaml"))
    assert m.entry_count == 0
    assert m.match("anything") is None


def test_reload(tmp_path):
    yaml_content = """
custom_answers:
  - id: "v1"
    topic: "general"
    enabled: true
    patterns:
      - "reload test"
    answer: "V1 answer"
"""
    yaml_file = tmp_path / "custom_answers.yaml"
    yaml_file.write_text(yaml_content)
    m = CustomAnswersMatcher(str(yaml_file))
    assert m.match("reload test") is not None

    # Overwrite with empty
    yaml_file.write_text("custom_answers: []\n")
    m.reload(str(yaml_file))
    assert m.match("reload test") is None
