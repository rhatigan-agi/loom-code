"""loom-code data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Memory:
    """A vectorized memory stored in the database."""

    id: str
    content: str
    memory_type: str
    project: str | None = None
    tags: list[str] = field(default_factory=list)
    embedding: bytes = b""
    salience: float = 0.5
    source_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0


@dataclass
class MemoryResult:
    """A memory with its similarity score from a search."""

    memory: Memory
    similarity: float


@dataclass
class Session:
    """A recorded work session."""

    id: str
    project: str
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    summary: str = ""
    learnings: list[str] = field(default_factory=list)
    surprises: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    file_path: str = ""


@dataclass
class Journal:
    """A narrative synthesis of sessions."""

    id: str
    project: str
    content: str = ""
    source_session_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    file_path: str = ""


@dataclass
class DirectiveChange:
    """A proposed change to a directive file."""

    id: str
    directive_file: str
    change_type: str  # "add", "modify", "remove"
    proposed_diff: str
    reasoning: str
    status: str = "pending"  # "pending", "approved", "rejected"
    source_reflection_id: str = ""
    proposed_at: datetime = field(default_factory=datetime.now)
    resolved_at: datetime | None = None


@dataclass
class Reflection:
    """A reflection cycle result."""

    id: str
    trigger: str
    sessions_analyzed: list[str] = field(default_factory=list)
    journals_analyzed: list[str] = field(default_factory=list)
    synthesis: str = ""
    proposed_changes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
