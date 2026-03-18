"""Tests for the file sync module."""

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# Set LOOM_HOME before importing
_test_dir = tempfile.mkdtemp(prefix="loom_test_")
os.environ["LOOM_HOME"] = _test_dir

from loom_mcp.file_sync import (
    apply_directive_diff,
    detect_changed_files,
    read_domain_directives,
    read_identity,
    read_permanent_directives,
    read_project_directives,
    slugify,
    write_journal_file,
    write_session_file,
)


@pytest.fixture(autouse=True)
def _fresh_dirs(tmp_path: Path) -> None:
    """Point config at tmp directory for each test."""
    import loom_mcp.config as cfg

    cfg.LOOM_HOME = tmp_path
    cfg.DIRECTIVES_DIR = tmp_path / "directives"
    cfg.DOMAIN_DIRECTIVES_DIR = cfg.DIRECTIVES_DIR / "by-domain"
    cfg.PROJECT_DIRECTIVES_DIR = cfg.DIRECTIVES_DIR / "by-project"
    cfg.SESSIONS_DIR = tmp_path / "sessions"
    cfg.JOURNALS_DIR = tmp_path / "journals"
    cfg.IDENTITY_FILE = tmp_path / "identity.md"
    cfg.PERMANENT_DIRECTIVES_FILE = cfg.DIRECTIVES_DIR / "permanent.md"

    cfg.DIRECTIVES_DIR.mkdir(parents=True, exist_ok=True)
    cfg.DOMAIN_DIRECTIVES_DIR.mkdir(parents=True, exist_ok=True)
    cfg.PROJECT_DIRECTIVES_DIR.mkdir(parents=True, exist_ok=True)
    cfg.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cfg.JOURNALS_DIR.mkdir(parents=True, exist_ok=True)


class TestSlugify:
    def test_basic_slug(self) -> None:
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert slugify("Fix bug #123!") == "fix-bug-123"

    def test_truncation(self) -> None:
        long = "a" * 100
        assert len(slugify(long)) <= 50

    def test_empty_string(self) -> None:
        assert slugify("") == ""


class TestWriteSessionFile:
    def test_creates_file(self) -> None:
        path = write_session_file(
            project="myproject",
            summary="Fixed the bug",
            learnings=["Learned about X"],
            surprises=["Y was unexpected"],
            tags=["python"],
            started_at=datetime(2025, 1, 15, 10, 30),
        )
        assert path.exists()
        content = path.read_text()
        assert "Fixed the bug" in content
        assert "Learned about X" in content
        assert "Y was unexpected" in content

    def test_creates_project_subdirectory(self) -> None:
        import loom_mcp.config as cfg

        path = write_session_file(
            project="newproject",
            summary="Test",
            learnings=[],
            surprises=[],
            tags=[],
            started_at=datetime.now(),
        )
        assert (cfg.SESSIONS_DIR / "newproject").is_dir()


class TestWriteJournalFile:
    def test_creates_file(self) -> None:
        path = write_journal_file(
            project="myproject",
            content="# Journal\nReflected on today's work.",
            created_at=datetime(2025, 1, 15),
        )
        assert path.exists()
        assert "Reflected" in path.read_text()
        assert "2025-01-15_myproject.md" in path.name


class TestReadDirectives:
    def test_read_missing_identity(self) -> None:
        assert read_identity() == ""

    def test_read_existing_identity(self) -> None:
        import loom_mcp.config as cfg

        cfg.IDENTITY_FILE.write_text("# I am a test identity")
        assert "test identity" in read_identity()

    def test_read_missing_permanent(self) -> None:
        assert read_permanent_directives() == ""

    def test_read_existing_permanent(self) -> None:
        import loom_mcp.config as cfg

        cfg.PERMANENT_DIRECTIVES_FILE.write_text("# Permanent rules")
        assert "Permanent rules" in read_permanent_directives()

    def test_read_domain_directives(self) -> None:
        import loom_mcp.config as cfg

        (cfg.DOMAIN_DIRECTIVES_DIR / "python.md").write_text("# Python rules")
        assert "Python rules" in read_domain_directives("python")
        assert read_domain_directives("rust") == ""

    def test_read_project_directives(self) -> None:
        import loom_mcp.config as cfg

        (cfg.PROJECT_DIRECTIVES_DIR / "myapp.md").write_text("# MyApp rules")
        assert "MyApp rules" in read_project_directives("myapp")


class TestApplyDirectiveDiff:
    def test_append_to_new_file(self) -> None:
        import loom_mcp.config as cfg

        apply_directive_diff("by-domain/rust.md", "APPEND:## Rust\n- Use cargo")
        filepath = cfg.DIRECTIVES_DIR / "by-domain" / "rust.md"
        assert filepath.exists()
        assert "Use cargo" in filepath.read_text()

    def test_replace_content(self) -> None:
        import loom_mcp.config as cfg

        filepath = cfg.DIRECTIVES_DIR / "test.md"
        filepath.write_text("old content")
        apply_directive_diff("test.md", "REPLACE:new content entirely")
        assert "new content entirely" in filepath.read_text()
        assert "old content" not in filepath.read_text()

    def test_targeted_replace_with_syntax(self) -> None:
        """REPLACE:...WITH: replaces a specific bullet without wiping the file."""
        import loom_mcp.config as cfg

        filepath = cfg.DIRECTIVES_DIR / "test.md"
        filepath.write_text("- old rule text\n\n- unrelated rule\n")
        diff = "REPLACE:\n- old rule text\n\nWITH:\n\n- new expanded rule text"
        apply_directive_diff("test.md", diff)
        content = filepath.read_text()
        assert "new expanded rule text" in content
        assert "old rule text" not in content
        assert "unrelated rule" in content  # rest of file preserved

    def test_targeted_replace_missing_target(self) -> None:
        """REPLACE:...WITH: with missing target is a no-op, not a file wipe."""
        import loom_mcp.config as cfg

        filepath = cfg.DIRECTIVES_DIR / "test.md"
        filepath.write_text("- some other rule\n")
        diff = "REPLACE:\n- nonexistent rule\n\nWITH:\n\n- replacement"
        apply_directive_diff("test.md", diff)
        assert filepath.read_text() == "- some other rule\n"  # unchanged

    def test_unknown_prefix_is_skipped(self) -> None:
        """Unknown ALL_CAPS: prefixes are skipped rather than appended literally."""
        import loom_mcp.config as cfg

        filepath = cfg.DIRECTIVES_DIR / "test.md"
        filepath.write_text("- existing rule\n")
        apply_directive_diff("test.md", "CONSOLIDATE: merge three rules into one")
        assert filepath.read_text() == "- existing rule\n"  # unchanged

    def test_default_append(self) -> None:
        import loom_mcp.config as cfg

        filepath = cfg.DIRECTIVES_DIR / "test.md"
        filepath.write_text("existing")
        apply_directive_diff("test.md", "new addition")
        content = filepath.read_text()
        assert "existing" in content
        assert "new addition" in content


class TestDetectChangedFiles:
    def test_detects_new_file(self) -> None:
        import loom_mcp.config as cfg

        (cfg.PERMANENT_DIRECTIVES_FILE).write_text("content")
        changed = detect_changed_files({})
        assert len(changed) >= 1

    def test_detects_modified_file(self) -> None:
        import loom_mcp.config as cfg
        import time

        cfg.PERMANENT_DIRECTIVES_FILE.write_text("original")
        mtimes = {str(cfg.PERMANENT_DIRECTIVES_FILE): cfg.PERMANENT_DIRECTIVES_FILE.stat().st_mtime}

        time.sleep(0.1)
        cfg.PERMANENT_DIRECTIVES_FILE.write_text("modified")

        changed = detect_changed_files(mtimes)
        assert cfg.PERMANENT_DIRECTIVES_FILE in changed
