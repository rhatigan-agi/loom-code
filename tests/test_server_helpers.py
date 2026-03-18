"""Tests for server helper functions."""

import os
import tempfile

_test_dir = tempfile.mkdtemp(prefix="loom_test_")
os.environ["LOOM_HOME"] = _test_dir

from loom_mcp.server import _extract_open_questions


class TestExtractOpenQuestions:
    def test_extracts_bullet_points(self) -> None:
        content = """\
## Summary
Some summary text.

**Open Questions / Unresolved**:
- Is the migration applied?
- What is the LLM routing decision?
- Why does the test fail on CI?

---

Narrative prose here.
"""
        questions = _extract_open_questions(content)
        assert len(questions) == 3
        assert "Is the migration applied?" in questions
        assert "What is the LLM routing decision?" in questions
        assert "Why does the test fail on CI?" in questions

    def test_returns_empty_when_section_missing(self) -> None:
        content = "## Summary\nNo open questions section here."
        assert _extract_open_questions(content) == []

    def test_handles_section_with_no_bullets(self) -> None:
        content = "**Open Questions / Unresolved**:\nNone at this time.\n---\n"
        assert _extract_open_questions(content) == []

    def test_stops_at_next_bold_header(self) -> None:
        content = """\
**Open Questions / Unresolved**:
- Question one

**Patterns Identified**:
- Not a question
"""
        questions = _extract_open_questions(content)
        assert questions == ["Question one"]

    def test_strips_leading_dash_and_whitespace(self) -> None:
        content = "**Open Questions**:\n-   Leading spaces here\n---\n"
        questions = _extract_open_questions(content)
        assert questions == ["Leading spaces here"]
