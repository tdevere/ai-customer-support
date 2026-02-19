"""
Custom-answers override layer.

Checks an incoming user message against a YAML file of hard-coded
high-confidence answers *before* the message is sent to the LLM pipeline.
When a match is found the orchestrator short-circuits directly to the
respond node, skipping topic classification, specialist agents, and the
verifier entirely.

This is analogous to Intercom Fin's "Custom Answers" feature – editorial
control over a small set of high-stakes or high-traffic replies.

Usage
-----
    from orchestrator.custom_answers import custom_answers_matcher

    match = custom_answers_matcher.match(user_message)
    if match:
        # match is a dict: id, topic, answer, confidence
        ...
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class CustomAnswersMatcher:
    """
    Load ``agents/custom_answers.yaml`` and test user messages against it.

    Matching strategy (in order)
    ----------------------------
    1. Exact substring  – any pattern appears verbatim in the lowercased message
    2. Whole-word regex – a word-boundary-anchored variant for short patterns
       (≤ 3 words) to avoid false positives on very short strings

    The first enabled entry whose *any* pattern matches wins.
    """

    def __init__(self, yaml_path: Optional[str] = None) -> None:
        if yaml_path is None:
            yaml_path = Path(__file__).parent.parent / "agents" / "custom_answers.yaml"
        self._entries: List[Dict[str, Any]] = self._load(yaml_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Test *message* against all enabled custom-answer entries.

        Returns
        -------
        dict with keys ``id``, ``topic``, ``answer``, ``confidence`` on the
        first match, or ``None`` if no entry matches.
        """
        normalised = message.lower().strip()
        # Collapse multiple whitespace for cleaner matching
        normalised = re.sub(r"\s+", " ", normalised)

        for entry in self._entries:
            if not entry.get("enabled", True):
                continue
            for pattern in entry.get("patterns", []):
                if self._matches(pattern.lower(), normalised):
                    return {
                        "id": entry["id"],
                        "topic": entry.get("topic", "general"),
                        "answer": entry["answer"].strip(),
                        "confidence": float(entry.get("confidence", 0.95)),
                    }
        return None

    def reload(self, yaml_path: Optional[str] = None) -> None:
        """Reload the YAML file.  Useful for hot-reloading in tests."""
        if yaml_path is None:
            yaml_path = Path(__file__).parent.parent / "agents" / "custom_answers.yaml"
        self._entries = self._load(yaml_path)

    @property
    def entry_count(self) -> int:
        """Number of loaded (including disabled) entries."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load(path) -> List[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            return data.get("custom_answers", []) if data else []
        except FileNotFoundError:
            # Graceful degradation: no custom answers configured
            return []

    @staticmethod
    def _matches(pattern: str, message: str) -> bool:
        """Return True if *pattern* appears in *message*."""
        # Primary: substring match
        if pattern in message:
            return True

        # Secondary: word-boundary regex for short patterns to avoid
        # matching "cost" inside "forecast" etc.
        word_count = len(pattern.split())
        if word_count <= 3:
            regex = r"\b" + re.escape(pattern) + r"\b"
            if re.search(regex, message):
                return True

        return False


# ---------------------------------------------------------------------------
# Module-level singleton used by the graph
# ---------------------------------------------------------------------------

custom_answers_matcher = CustomAnswersMatcher()
