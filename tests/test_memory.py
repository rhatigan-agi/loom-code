"""Tests for the memory manager."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Set LOOM_HOME before importing modules that use config
_test_dir = tempfile.mkdtemp(prefix="loom_test_")
os.environ["LOOM_HOME"] = _test_dir

from loom_mcp.config import DB_PATH
from loom_mcp.init_db import get_connection, init_database
from loom_mcp.memory import (
    archive_memories,
    decay_memories,
    get_high_salience_memories,
    get_memory_stats,
    get_recent_journals,
    get_recent_sessions,
    reinforce_memory,
    search_memories,
    store_journal,
    store_memory,
    store_session,
)
from loom_mcp.models import Journal, Session


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path: Path) -> None:
    """Use a fresh database for each test."""
    import loom_mcp.config as cfg

    cfg.LOOM_HOME = tmp_path
    cfg.DB_DIR = tmp_path / "db"
    cfg.DB_PATH = cfg.DB_DIR / "loom.db"
    cfg.SESSIONS_DIR = tmp_path / "sessions"
    cfg.JOURNALS_DIR = tmp_path / "journals"
    cfg.DIRECTIVES_DIR = tmp_path / "directives"
    cfg.DOMAIN_DIRECTIVES_DIR = cfg.DIRECTIVES_DIR / "by-domain"
    cfg.PROJECT_DIRECTIVES_DIR = cfg.DIRECTIVES_DIR / "by-project"
    cfg.MODEL_CACHE_DIR = tmp_path / ".model-cache"

    cfg.DB_DIR.mkdir(parents=True, exist_ok=True)
    cfg.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cfg.JOURNALS_DIR.mkdir(parents=True, exist_ok=True)
    cfg.DIRECTIVES_DIR.mkdir(parents=True, exist_ok=True)
    cfg.DOMAIN_DIRECTIVES_DIR.mkdir(parents=True, exist_ok=True)
    cfg.PROJECT_DIRECTIVES_DIR.mkdir(parents=True, exist_ok=True)

    init_database()


class TestStoreMemory:
    def test_store_and_retrieve(self) -> None:
        memory_id = store_memory(
            content="Python uses indentation for blocks",
            memory_type="indexed",
            project="test",
            tags=["python", "syntax"],
        )
        assert memory_id
        assert len(memory_id) == 12

    def test_near_duplicate_deduplication(self) -> None:
        id1 = store_memory("Python uses indentation", "indexed", "test")
        id2 = store_memory("Python uses indentation", "indexed", "test")
        # Exact duplicate should return same ID (reinforced)
        assert id1 == id2

    def test_different_content_gets_different_id(self) -> None:
        id1 = store_memory("Python programming", "indexed", "test")
        id2 = store_memory("Chocolate cake recipe instructions step by step", "indexed", "test")
        assert id1 != id2


class TestSearchMemories:
    def test_search_finds_relevant(self) -> None:
        store_memory("Python exception handling with try-except", "indexed", "test")
        store_memory("Baking chocolate cake in the oven", "indexed", "test")

        results = search_memories("python error handling", project="test")
        assert len(results) > 0
        assert "python" in results[0].memory.content.lower() or "exception" in results[0].memory.content.lower()

    def test_search_empty_db(self) -> None:
        results = search_memories("anything")
        assert results == []

    def test_search_respects_limit(self) -> None:
        for i in range(10):
            store_memory(f"Memory number {i} about testing", "indexed", "test")

        results = search_memories("testing", project="test", limit=3)
        assert len(results) <= 3

    def test_search_filters_by_type(self) -> None:
        store_memory("Python tip", "indexed", "test")
        store_memory("Session summary", "session", "test")

        results = search_memories("Python", project="test", memory_type="indexed")
        for r in results:
            assert r.memory.memory_type == "indexed"


class TestReinforce:
    def test_reinforce_bumps_salience(self) -> None:
        memory_id = store_memory("test content", "indexed", "test")

        conn = get_connection()
        row_before = conn.execute(
            "SELECT salience, access_count FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        conn.close()

        reinforce_memory(memory_id)

        conn = get_connection()
        row_after = conn.execute(
            "SELECT salience, access_count FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        conn.close()

        assert row_after["salience"] > row_before["salience"]
        assert row_after["access_count"] > row_before["access_count"]


class TestDecay:
    def test_decay_reduces_salience(self) -> None:
        memory_id = store_memory("old memory", "indexed", "test")

        # Manually backdate the accessed_at
        conn = get_connection()
        conn.execute(
            "UPDATE memories SET accessed_at = '2020-01-01T00:00:00' WHERE id = ?",
            (memory_id,),
        )
        conn.commit()
        conn.close()

        count = decay_memories(days_threshold=1, rate=0.5)
        assert count >= 1

        conn = get_connection()
        row = conn.execute(
            "SELECT salience FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        conn.close()
        assert row["salience"] < 0.5


class TestJournalDecayImmunity:
    def test_journal_memories_are_not_decayed(self) -> None:
        memory_id = store_memory("journal content", "journal", "test", salience=0.65)

        conn = get_connection()
        conn.execute(
            "UPDATE memories SET accessed_at = '2020-01-01T00:00:00' WHERE id = ?",
            (memory_id,),
        )
        conn.commit()
        conn.close()

        count = decay_memories(days_threshold=1, rate=0.5)

        conn = get_connection()
        row = conn.execute(
            "SELECT salience FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        conn.close()

        # Journal memory must not have decayed
        assert row["salience"] == pytest.approx(0.65)

    def test_non_journal_memories_still_decay(self) -> None:
        memory_id = store_memory("indexed content", "indexed", "test")

        conn = get_connection()
        conn.execute(
            "UPDATE memories SET accessed_at = '2020-01-01T00:00:00' WHERE id = ?",
            (memory_id,),
        )
        conn.commit()
        conn.close()

        count = decay_memories(days_threshold=1, rate=0.5)
        assert count >= 1


class TestGetRecentJournals:
    def test_returns_journals_newest_first(self) -> None:
        j1 = Journal(id="j001", project="proj", content="first journal")
        j2 = Journal(id="j002", project="proj", content="second journal")
        store_journal(j1)
        store_journal(j2)

        results = get_recent_journals("proj", limit=5)
        assert len(results) == 2
        # newest first — j2 was inserted after j1
        assert results[0].id == "j002"
        assert results[1].id == "j001"

    def test_respects_limit(self) -> None:
        for i in range(5):
            store_journal(Journal(id=f"j{i:03d}", project="proj", content=f"journal {i}"))

        results = get_recent_journals("proj", limit=3)
        assert len(results) == 3

    def test_returns_empty_for_unknown_project(self) -> None:
        results = get_recent_journals("no-such-project", limit=5)
        assert results == []

    def test_filters_by_project(self) -> None:
        store_journal(Journal(id="ja1", project="alpha", content="alpha journal"))
        store_journal(Journal(id="jb1", project="beta", content="beta journal"))

        results = get_recent_journals("alpha", limit=5)
        assert len(results) == 1
        assert results[0].project == "alpha"


class TestSessions:
    def test_store_and_get_sessions(self) -> None:
        session = Session(id="test123", project="myproject", summary="did stuff")
        store_session(session)

        recent = get_recent_sessions("myproject")
        assert len(recent) == 1
        assert recent[0].summary == "did stuff"


class TestStats:
    def test_stats_on_empty_db(self) -> None:
        stats = get_memory_stats()
        assert stats["total_memories"] == 0
        assert stats["total_sessions"] == 0

    def test_stats_after_inserts(self) -> None:
        store_memory("test", "indexed", "test")
        stats = get_memory_stats()
        assert stats["total_memories"] == 1


class TestArchiveMemories:
    def test_archives_specified_memories(self) -> None:
        mid1 = store_memory("content one about archiving", "indexed", salience=0.8)
        mid2 = store_memory("content two about retrieval", "indexed", salience=0.8)
        count = archive_memories([mid1])
        assert count == 1
        high = get_high_salience_memories(threshold=0.3)
        ids = [m.id for m in high]
        assert mid1 not in ids
        assert mid2 in ids

    def test_archive_empty_list_returns_zero(self) -> None:
        assert archive_memories([]) == 0

    def test_archive_nonexistent_id_returns_zero(self) -> None:
        assert archive_memories(["nonexistent"]) == 0
