"""loom-code SQLite schema initialization."""

import logging
import sqlite3

import loom_mcp.config as cfg

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    project TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    embedding BLOB,
    salience REAL NOT NULL DEFAULT 0.5,
    source_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project);
CREATE INDEX IF NOT EXISTS idx_memories_salience ON memories(salience DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    summary TEXT NOT NULL DEFAULT '',
    learnings TEXT NOT NULL DEFAULT '[]',
    surprises TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    file_path TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);

CREATE TABLE IF NOT EXISTS journals (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    source_session_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    file_path TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_journals_project ON journals(project);
CREATE INDEX IF NOT EXISTS idx_journals_created ON journals(created_at DESC);

CREATE TABLE IF NOT EXISTS directive_changes (
    id TEXT PRIMARY KEY,
    directive_file TEXT NOT NULL,
    change_type TEXT NOT NULL,
    proposed_diff TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    source_reflection_id TEXT NOT NULL DEFAULT '',
    proposed_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_dc_status ON directive_changes(status);

CREATE TABLE IF NOT EXISTS reflections (
    id TEXT PRIMARY KEY,
    trigger TEXT NOT NULL,
    sessions_analyzed TEXT NOT NULL DEFAULT '[]',
    journals_analyzed TEXT NOT NULL DEFAULT '[]',
    synthesis TEXT NOT NULL DEFAULT '',
    proposed_changes TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reflections_created ON reflections(created_at DESC);
"""


def init_database() -> None:
    """Create the SQLite database and all tables if they don't exist."""
    cfg.DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cfg.DB_PATH))
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.info("Database initialized", extra={"path": str(cfg.DB_PATH)})
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    """Get a connection to the database, initializing if needed."""
    if not cfg.DB_PATH.exists():
        init_database()
    conn = sqlite3.connect(str(cfg.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
