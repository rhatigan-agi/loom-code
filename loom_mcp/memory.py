"""loom-code memory manager: store, search, reinforce, decay."""

import json
import logging
import uuid
from datetime import datetime, timedelta

from loom_mcp.config import (
    ARCHIVE_SALIENCE_THRESHOLD,
    DECAY_RATE,
    DEFAULT_SALIENCE,
    NEAR_DUPLICATE_THRESHOLD,
)
from loom_mcp.embeddings import embed, search
from loom_mcp.init_db import get_connection
from loom_mcp.models import (
    DirectiveChange,
    Journal,
    Memory,
    MemoryResult,
    Reflection,
    Session,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


def _row_to_memory(row: dict) -> Memory:
    """Convert a database row to a Memory dataclass."""
    return Memory(
        id=row["id"],
        content=row["content"],
        memory_type=row["memory_type"],
        project=row["project"],
        tags=json.loads(row["tags"]),
        embedding=row["embedding"] or b"",
        salience=row["salience"],
        source_ids=json.loads(row["source_ids"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        accessed_at=datetime.fromisoformat(row["accessed_at"]),
        access_count=row["access_count"],
    )


def store_memory(
    content: str,
    memory_type: str,
    project: str | None = None,
    tags: list[str] | None = None,
    source_ids: list[str] | None = None,
    salience: float = DEFAULT_SALIENCE,
) -> str:
    """Embed and store a memory, deduplicating against near-duplicates.

    Args:
        content: The memory content text.
        memory_type: Category (e.g. "indexed", "session",
            "journal", "reconsolidated_insight").
        project: Optional project scope. None = global (visible to all projects).
        tags: Optional list of tags.
        source_ids: Optional list of source memory/session IDs.
        salience: Initial salience score (default 0.5). Use higher values for
            distilled insights (e.g. 0.7 for reconsolidated, 0.65 for journals).

    Returns:
        The memory ID (new or existing duplicate).
    """
    tags = tags or []
    source_ids = source_ids or []

    embedding = embed(content)

    # Check for near-duplicates
    conn = get_connection()
    try:
        query = "SELECT id, embedding FROM memories WHERE memory_type = ?"
        params: list[str] = [memory_type]
        if project:
            query += " AND project = ?"
            params.append(project)

        rows = conn.execute(query, params).fetchall()
        candidates = [(r["id"], r["embedding"]) for r in rows if r["embedding"]]

        if candidates:
            ranked = search(embedding, candidates)
            if ranked and ranked[0][1] > NEAR_DUPLICATE_THRESHOLD:
                existing_id = ranked[0][0]
                logger.info(
                    "Near-duplicate found, reinforcing existing",
                    extra={"existing_id": existing_id, "similarity": ranked[0][1]},
                )
                reinforce_memory(existing_id)
                return existing_id

        memory_id = _gen_id()
        now = _now_iso()
        conn.execute(
            """INSERT INTO memories
               (id, content, memory_type, project, tags, embedding, salience,
                source_ids, created_at, updated_at, accessed_at, access_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                memory_id,
                content,
                memory_type,
                project,
                json.dumps(tags),
                embedding,
                salience,
                json.dumps(source_ids),
                now,
                now,
                now,
                0,
            ),
        )
        conn.commit()
        logger.info(
            "Memory stored",
            extra={"id": memory_id, "type": memory_type, "project": project},
        )
        return memory_id
    finally:
        conn.close()


def search_memories(
    query: str,
    project: str | None = None,
    memory_type: str | None = None,
    limit: int = 5,
    min_salience: float = 0.0,
) -> list[MemoryResult]:
    """Semantic search over memories.

    Args:
        query: Natural language search query.
        project: Optional project filter.
        memory_type: Optional type filter.
        limit: Maximum results to return.
        min_salience: Minimum salience threshold.

    Returns:
        List of MemoryResult sorted by similarity.
    """
    query_emb = embed(query)

    conn = get_connection()
    try:
        sql = "SELECT * FROM memories WHERE salience >= ?"
        params: list[str | float] = [min_salience]

        if project:
            sql += " AND (project = ? OR project IS NULL)"
            params.append(project)
        if memory_type:
            sql += " AND memory_type = ?"
            params.append(memory_type)

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return []

        candidates = [
            (dict(r)["id"], dict(r)["embedding"])
            for r in rows
            if dict(r)["embedding"]
        ]
        row_map = {dict(r)["id"]: dict(r) for r in rows}

        ranked = search(query_emb, candidates)
        results: list[MemoryResult] = []
        for memory_id, score in ranked[:limit]:
            memory = _row_to_memory(row_map[memory_id])
            results.append(MemoryResult(memory=memory, similarity=score))
            reinforce_memory(memory_id)

        return results
    finally:
        conn.close()


def reinforce_memory(memory_id: str) -> None:
    """Bump salience and access metadata for a memory."""
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            """UPDATE memories
               SET salience = MIN(salience + 0.05, 1.0),
                   accessed_at = ?,
                   access_count = access_count + 1,
                   updated_at = ?
               WHERE id = ?""",
            (now, now, memory_id),
        )
        conn.commit()
    finally:
        conn.close()


def decay_memories(days_threshold: int = 14, rate: float = DECAY_RATE) -> int:
    """Apply entropy decay to stale memories.

    Args:
        days_threshold: Days since last access before decay applies.
        rate: Multiplicative decay factor.

    Returns:
        Number of memories decayed.
    """
    conn = get_connection()
    try:
        cutoff = (datetime.now() - timedelta(days=days_threshold)).isoformat()
        # Reconsolidated insights are immune for RECONSOLIDATION_IMMUNITY_DAYS
        from loom_mcp.config import RECONSOLIDATION_IMMUNITY_DAYS

        immunity_cutoff = (
            datetime.now() - timedelta(days=RECONSOLIDATION_IMMUNITY_DAYS)
        ).isoformat()

        result = conn.execute(
            """UPDATE memories
               SET salience = salience * ?, updated_at = ?
               WHERE accessed_at < ?
                 AND salience > ?
                 AND memory_type != 'journal'
                 AND NOT (memory_type = 'reconsolidated_insight' AND created_at > ?)""",
            (rate, _now_iso(), cutoff, ARCHIVE_SALIENCE_THRESHOLD, immunity_cutoff),
        )
        conn.commit()
        count = result.rowcount
        logger.info("Decay applied", extra={"decayed_count": count, "rate": rate})
        return count
    finally:
        conn.close()


def archive_memories(ids: list[str]) -> int:
    """Archive memories by setting salience to 0.1 (below fetch thresholds).

    Memories remain in the DB but won't surface in normal queries.

    Args:
        ids: List of memory IDs to archive.

    Returns:
        Number of memories actually archived.
    """
    if not ids:
        return 0
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(ids))
        result = conn.execute(
            f"UPDATE memories SET salience = 0.1, updated_at = ? WHERE id IN ({placeholders})",
            [_now_iso(), *ids],
        )
        conn.commit()
        logger.info("Memories archived", extra={"count": result.rowcount})
        return result.rowcount
    finally:
        conn.close()


def get_memories_by_ids(ids: list[str]) -> list[Memory]:
    """Fetch memories by a list of IDs.

    Args:
        ids: List of memory IDs to fetch.

    Returns:
        List of Memory objects for the given IDs.
    """
    if not ids:
        return []
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT * FROM memories WHERE id IN ({placeholders})", ids
        ).fetchall()
        return [_row_to_memory(dict(r)) for r in rows]
    finally:
        conn.close()


def get_high_salience_memories(
    project: str | None = None,
    threshold: float = 0.8,
    limit: int = 10,
    memory_type: str | None = None,
) -> list[Memory]:
    """Fetch high-salience memories for a project."""
    conn = get_connection()
    try:
        sql = "SELECT * FROM memories WHERE salience >= ?"
        params: list[str | float] = [threshold]
        if project:
            sql += " AND (project = ? OR project IS NULL)"
            params.append(project)
        if memory_type:
            sql += " AND memory_type = ?"
            params.append(memory_type)
        sql += " ORDER BY salience DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [_row_to_memory(dict(r)) for r in rows]
    finally:
        conn.close()


def store_session(session: Session) -> str:
    """Store a session record in the database."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO sessions
               (id, project, started_at, ended_at, summary, learnings,
                surprises, tags, file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.id,
                session.project,
                session.started_at.isoformat(),
                session.ended_at.isoformat() if session.ended_at else None,
                session.summary,
                json.dumps(session.learnings),
                json.dumps(session.surprises),
                json.dumps(session.tags),
                session.file_path,
            ),
        )
        conn.commit()
        logger.info(
            "Session stored",
            extra={"id": session.id, "project": session.project},
        )
        return session.id
    finally:
        conn.close()


def get_recent_sessions(project: str, limit: int = 5) -> list[Session]:
    """Fetch recent sessions for a project."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE project = ? ORDER BY started_at DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return [
            Session(
                id=r["id"],
                project=r["project"],
                started_at=datetime.fromisoformat(r["started_at"]),
                ended_at=(
                    datetime.fromisoformat(r["ended_at"])
                    if r["ended_at"]
                    else None
                ),
                summary=r["summary"],
                learnings=json.loads(r["learnings"]),
                surprises=json.loads(r["surprises"]),
                tags=json.loads(r["tags"]),
                file_path=r["file_path"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def get_sessions_since(project: str, since: datetime) -> list[Session]:
    """Fetch sessions for a project since a given date."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM sessions
               WHERE project = ? AND started_at >= ?
               ORDER BY started_at ASC""",
            (project, since.isoformat()),
        ).fetchall()
        return [
            Session(
                id=r["id"],
                project=r["project"],
                started_at=datetime.fromisoformat(r["started_at"]),
                ended_at=(
                    datetime.fromisoformat(r["ended_at"])
                    if r["ended_at"]
                    else None
                ),
                summary=r["summary"],
                learnings=json.loads(r["learnings"]),
                surprises=json.loads(r["surprises"]),
                tags=json.loads(r["tags"]),
                file_path=r["file_path"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def store_journal(journal: Journal) -> str:
    """Store a journal entry in the database."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO journals
               (id, project, content, source_session_ids, created_at, file_path)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                journal.id,
                journal.project,
                journal.content,
                json.dumps(journal.source_session_ids),
                journal.created_at.isoformat(),
                journal.file_path,
            ),
        )
        conn.commit()
        logger.info(
            "Journal stored",
            extra={
                "id": journal.id,
                "project": journal.project,
            },
        )
        return journal.id
    finally:
        conn.close()


def get_latest_journal(project: str) -> Journal | None:
    """Fetch the most recent journal for a project."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM journals WHERE project = ? ORDER BY created_at DESC LIMIT 1",
            (project,),
        ).fetchone()
        if not row:
            return None
        return Journal(
            id=row["id"],
            project=row["project"],
            content=row["content"],
            source_session_ids=json.loads(row["source_session_ids"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            file_path=row["file_path"],
        )
    finally:
        conn.close()


def get_recent_journals(project: str, limit: int = 3) -> list[Journal]:
    """Fetch the most recent journals for a project.

    Args:
        project: Project name to filter by.
        limit: Maximum number of journals to return.

    Returns:
        List of Journal entries ordered newest-first.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM journals WHERE project = ? ORDER BY created_at DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return [
            Journal(
                id=r["id"],
                project=r["project"],
                content=r["content"],
                source_session_ids=json.loads(r["source_session_ids"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                file_path=r["file_path"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def store_directive_change(change: DirectiveChange) -> str:
    """Store a proposed directive change."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO directive_changes
               (id, directive_file, change_type, proposed_diff, reasoning,
                status, source_reflection_id, proposed_at, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                change.id,
                change.directive_file,
                change.change_type,
                change.proposed_diff,
                change.reasoning,
                change.status,
                change.source_reflection_id,
                change.proposed_at.isoformat(),
                change.resolved_at.isoformat() if change.resolved_at else None,
            ),
        )
        conn.commit()
        logger.info(
            "Directive change stored",
            extra={
                "id": change.id,
                "status": change.status,
            },
        )
        return change.id
    finally:
        conn.close()


def resolve_directive_change(change_id: str, status: str) -> None:
    """Approve or reject a directive change proposal."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE directive_changes
               SET status = ?, resolved_at = ?
               WHERE id = ?""",
            (status, _now_iso(), change_id),
        )
        conn.commit()
        logger.info(
            "Directive change resolved",
            extra={"id": change_id, "status": status},
        )
    finally:
        conn.close()


def get_pending_directive_changes() -> list[DirectiveChange]:
    """Fetch all pending directive change proposals."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM directive_changes"
            " WHERE status = 'pending'"
            " ORDER BY proposed_at DESC",
        ).fetchall()
        return [
            DirectiveChange(
                id=r["id"],
                directive_file=r["directive_file"],
                change_type=r["change_type"],
                proposed_diff=r["proposed_diff"],
                reasoning=r["reasoning"],
                status=r["status"],
                source_reflection_id=r["source_reflection_id"],
                proposed_at=datetime.fromisoformat(r["proposed_at"]),
                resolved_at=(
                    datetime.fromisoformat(r["resolved_at"])
                    if r["resolved_at"]
                    else None
                ),
            )
            for r in rows
        ]
    finally:
        conn.close()


def get_directive_change(change_id: str) -> DirectiveChange | None:
    """Fetch a single directive change by ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM directive_changes WHERE id = ?",
            (change_id,),
        ).fetchone()
        if not row:
            return None
        return DirectiveChange(
            id=row["id"],
            directive_file=row["directive_file"],
            change_type=row["change_type"],
            proposed_diff=row["proposed_diff"],
            reasoning=row["reasoning"],
            status=row["status"],
            source_reflection_id=row["source_reflection_id"],
            proposed_at=datetime.fromisoformat(row["proposed_at"]),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"])
                if row["resolved_at"]
                else None
            ),
        )
    finally:
        conn.close()


def store_reflection(reflection: Reflection) -> str:
    """Store a reflection cycle result."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO reflections
               (id, trigger, sessions_analyzed, journals_analyzed,
                synthesis, proposed_changes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                reflection.id,
                reflection.trigger,
                json.dumps(reflection.sessions_analyzed),
                json.dumps(reflection.journals_analyzed),
                reflection.synthesis,
                json.dumps(reflection.proposed_changes),
                reflection.created_at.isoformat(),
            ),
        )
        conn.commit()
        logger.info("Reflection stored", extra={"id": reflection.id})
        return reflection.id
    finally:
        conn.close()


def get_memory_stats() -> dict:
    """Get aggregate stats about the memory system."""
    conn = get_connection()
    try:
        stats: dict = {}

        row = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()
        stats["total_memories"] = row["c"]

        row = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE salience >= 0.8"
        ).fetchone()
        stats["high_salience_memories"] = row["c"]

        row = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE salience < 0.1"
        ).fetchone()
        stats["archive_candidates"] = row["c"]

        row = conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()
        stats["total_sessions"] = row["c"]

        row = conn.execute("SELECT COUNT(*) as c FROM journals").fetchone()
        stats["total_journals"] = row["c"]

        row = conn.execute(
            "SELECT COUNT(*) as c FROM directive_changes WHERE status = 'pending'"
        ).fetchone()
        stats["pending_changes"] = row["c"]

        row = conn.execute("SELECT COUNT(*) as c FROM reflections").fetchone()
        stats["total_reflections"] = row["c"]

        row = conn.execute("SELECT AVG(salience) as avg FROM memories").fetchone()
        stats["avg_salience"] = round(row["avg"] or 0.0, 3)

        # Breakdown by memory_type
        rows = conn.execute(
            "SELECT memory_type, COUNT(*) as c FROM memories"
            " GROUP BY memory_type ORDER BY c DESC"
        ).fetchall()
        stats["by_type"] = {r["memory_type"]: r["c"] for r in rows}

        # Breakdown by project (NULL = global cross-project memories)
        rows = conn.execute(
            "SELECT COALESCE(project, '(global)') as proj, COUNT(*) as c"
            " FROM memories GROUP BY proj ORDER BY c DESC"
        ).fetchall()
        stats["by_project"] = {r["proj"]: r["c"] for r in rows}

        # Global (project=NULL) vs project-scoped split
        row = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE project IS NULL"
        ).fetchone()
        stats["global_memories"] = row["c"]

        return stats
    finally:
        conn.close()
