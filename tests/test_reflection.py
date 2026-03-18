"""Tests for the reflection pipeline.

These tests mock _call_claude to avoid requiring an API key or CLI.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_test_dir = tempfile.mkdtemp(prefix="loom_test_")
os.environ["LOOM_HOME"] = _test_dir

from loom_mcp.init_db import init_database
from loom_mcp.memory import store_memory, store_session
from loom_mcp.models import Session
from loom_mcp.reflection import (
    _propose_directives,
    _reconsolidate_memories,
    _synthesize_journal,
    run_reflection,
)


@pytest.fixture(autouse=True)
def _fresh_env(tmp_path: Path) -> None:
    """Point config at tmp directory for each test."""
    import loom_mcp.config as cfg

    cfg.LOOM_HOME = tmp_path
    cfg.DB_DIR = tmp_path / "db"
    cfg.DB_PATH = cfg.DB_DIR / "loom.db"
    cfg.SESSIONS_DIR = tmp_path / "sessions"
    cfg.JOURNALS_DIR = tmp_path / "journals"
    cfg.DIRECTIVES_DIR = tmp_path / "directives"
    cfg.DOMAIN_DIRECTIVES_DIR = cfg.DIRECTIVES_DIR / "by-domain"
    cfg.PROJECT_DIRECTIVES_DIR = cfg.DIRECTIVES_DIR / "by-project"
    cfg.PERMANENT_DIRECTIVES_FILE = cfg.DIRECTIVES_DIR / "permanent.md"
    cfg.IDENTITY_FILE = tmp_path / "identity.md"
    cfg.MODEL_CACHE_DIR = tmp_path / ".model-cache"

    for d in [
        cfg.DB_DIR, cfg.SESSIONS_DIR, cfg.JOURNALS_DIR,
        cfg.DIRECTIVES_DIR, cfg.DOMAIN_DIRECTIVES_DIR,
        cfg.PROJECT_DIRECTIVES_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    cfg.PERMANENT_DIRECTIVES_FILE.write_text("# Test directives\n- Be helpful")
    init_database()


class TestSynthesizeJournal:
    @patch("loom_mcp.reflection._call_claude")
    def test_returns_journal_text(self, mock_call: MagicMock) -> None:
        mock_call.return_value = "Today I worked on improving the test suite..."

        sessions = [
            {"date": "2025-01-15", "summary": "Fixed tests", "learnings": ["mocks work"], "surprises": []},
        ]
        result = _synthesize_journal("test-project", sessions)
        assert "test suite" in result
        mock_call.assert_called_once()


class TestProposeDirectives:
    @patch("loom_mcp.reflection._call_claude")
    def test_parses_json_proposals(self, mock_call: MagicMock) -> None:
        mock_call.return_value = json.dumps([
            {
                "file": "permanent.md",
                "change_type": "add",
                "diff": "APPEND:## New Rule\n- Always test",
                "reasoning": "Observed in 3 sessions",
            }
        ])

        result = _propose_directives(
            project="test",
            current_directives="# Existing",
            sessions=[{"date": "2025-01-15", "summary": "test", "learnings": []}],
            journals=[],
            memories=[],
        )
        assert len(result) == 1
        assert result[0]["file"] == "permanent.md"

    @patch("loom_mcp.reflection._call_claude")
    def test_handles_empty_proposals(self, mock_call: MagicMock) -> None:
        mock_call.return_value = "[]"
        result = _propose_directives("test", "", [], [], [])
        assert result == []

    @patch("loom_mcp.reflection._call_claude")
    def test_handles_invalid_json(self, mock_call: MagicMock) -> None:
        mock_call.return_value = "I couldn't find any patterns."
        result = _propose_directives("test", "", [], [], [])
        assert result == []


class TestReconsolidateMemories:
    @patch("loom_mcp.reflection._call_claude")
    def test_returns_insights(self, mock_call: MagicMock) -> None:
        mock_call.return_value = json.dumps({
            "insights": [
                {
                    "content": "Error handling patterns in Python and TypeScript share common retry logic",
                    "cross_project": False,
                    "captures_ids": ["mem1"],
                }
            ],
            "supersede": [],
        })

        insights, supersede_ids = _reconsolidate_memories(
            memories=[{"id": "mem1", "content": "retry logic", "type": "indexed", "project": "test-proj", "salience": 0.8, "tags": []}],
            sessions=[{"date": "2025-01-15", "summary": "worked on retries"}],
        )
        assert len(insights) == 1
        assert "retry" in insights[0].content.lower()
        assert supersede_ids == []

    def test_empty_memories(self) -> None:
        insights, supersede_ids = _reconsolidate_memories([], [])
        assert insights == []
        assert supersede_ids == []


class TestRunReflection:
    @patch("loom_mcp.reflection._call_claude")
    def test_no_sessions_returns_early(self, mock_call: MagicMock) -> None:
        result = run_reflection(days=7, project="empty-project")
        assert result["status"] == "no_sessions"
        mock_call.assert_not_called()

    @patch("loom_mcp.reflection._call_claude")
    def test_full_reflection_with_sessions(self, mock_call: MagicMock) -> None:
        session = Session(
            id="sess1",
            project="test",
            summary="Implemented feature X",
            learnings=["Learned about caching"],
            started_at=datetime.now() - timedelta(hours=2),
        )
        store_session(session)

        # One call per step: journal, directives, reconsolidation
        mock_call.side_effect = [
            "Journal: Today I implemented feature X...",
            json.dumps([]),  # No directive proposals
            json.dumps({"insights": [], "supersede": []}),  # No reconsolidation insights
        ]

        result = run_reflection(days=7, project="test", mode="full")
        assert result["status"] == "complete"
        assert "journal" in result
        assert result["sessions_analyzed"] == 1
