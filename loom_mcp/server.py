"""loom-code MCP server: 8 tools for persistent memory and self-evolution."""

import json
import logging
import re
from datetime import datetime

from fastmcp import FastMCP

from loom_mcp.config import ACTIVE_SESSIONS_DIR, HIGH_SALIENCE_THRESHOLD, PENDING_CAPTURES_DIR
from loom_mcp.file_sync import (
    apply_directive_diff,
    find_similar_directive,
    read_domain_directives,
    read_identity,
    read_permanent_directives,
    read_project_directives,
    write_session_file,
)
from loom_mcp.memory import (
    _gen_id,
    archive_memories,
    get_directive_change,
    get_high_salience_memories,
    get_latest_journal,
    get_memory_stats,
    get_pending_directive_changes,
    get_recent_sessions,
    resolve_directive_change,
    search_memories,
    store_directive_change,
    store_memory,
    store_session,
)
from loom_mcp.models import DirectiveChange, Session

logger = logging.getLogger(__name__)


def _coerce_list(val: list[str] | str | None) -> list[str]:
    """Accept a list or a JSON-encoded string — coerce to list."""
    if val is None:
        return []
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return [v.strip() for v in val.strip("[]").split(",") if v.strip()]
    return val


mcp = FastMCP(
    "loom-code",
    instructions="Persistent memory and self-evolving directives for Claude Code",
)

# Track active sessions in memory (process lifetime)
_active_sessions: dict[str, Session] = {}

# Known project domains (accumulated over sessions)
_project_domains: dict[str, set[str]] = {}


def _extract_open_questions(content: str) -> list[str]:
    """Extract bullet points from the Open Questions section of a journal."""
    match = re.search(
        r"\*\*Open Questions[^*]*\*\*:?\s*\n(.*?)(?:\n---|\n\*\*|\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return []
    return [
        line.lstrip("- ").strip()
        for line in match.group(1).splitlines()
        if line.strip().startswith("- ")
    ]


@mcp.tool()
def loom_session_start(project: str) -> dict:
    """Boot sequence: load identity, directives, and recent context for a project.

    IMPORTANT: Call this only from the main Claude Code session. Sub-agents
    (Explore, Plan, Bash, general-purpose, etc.) must never call this tool.

    Args:
        project: The project name to start a session for.
    """
    session_id = _gen_id()
    session = Session(id=session_id, project=project)
    _active_sessions[project] = session
    ACTIVE_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (ACTIVE_SESSIONS_DIR / project).touch()

    # Load identity
    identity = read_identity()

    # Load directives
    permanent = read_permanent_directives()
    project_directives = read_project_directives(project)

    # Load domain directives based on known domains
    domain_directives: dict[str, str] = {}
    for domain in _project_domains.get(project, set()):
        content = read_domain_directives(domain)
        if content:
            domain_directives[domain] = content

    # Fetch recent session summaries
    recent_sessions = get_recent_sessions(project, limit=5)
    session_summaries = [
        {
            "date": s.started_at.isoformat(),
            "summary": s.summary,
            "learnings": s.learnings,
        }
        for s in recent_sessions
    ]

    # Fetch high-salience memories
    high_salience = get_high_salience_memories(
        project=project, threshold=HIGH_SALIENCE_THRESHOLD, limit=10
    )
    salient_memories = [
        {
            "content": m.content,
            "type": m.memory_type,
            "salience": round(m.salience, 2),
            "tags": m.tags,
        }
        for m in high_salience
    ]

    # Check pending directive changes
    pending = get_pending_directive_changes()
    pending_changes = [
        {
            "id": c.id,
            "file": c.directive_file,
            "type": c.change_type,
            "reasoning": c.reasoning,
        }
        for c in pending
    ]

    # Drain pending-captures queue — memories queued by PreCompact / SubagentStop hooks
    captured_count = 0
    if PENDING_CAPTURES_DIR.exists():
        for capture_file in sorted(PENDING_CAPTURES_DIR.glob("*.json")):
            try:
                record = json.loads(capture_file.read_text())
                store_memory(
                    content=record["content"],
                    memory_type=record["memory_type"],
                    project=record.get("project"),
                    tags=record.get("tags"),
                    salience=record.get("salience", 0.5),
                )
                capture_file.unlink()
                captured_count += 1
            except Exception as exc:
                logger.warning("Failed to process pending capture %s: %s", capture_file.name, exc)

    # Surface open questions from the last journal so unresolved threads carry forward
    latest_journal = get_latest_journal(project)
    last_journal_context: dict | None = None
    if latest_journal:
        open_questions = _extract_open_questions(latest_journal.content)
        last_journal_context = {
            "date": latest_journal.created_at.isoformat()[:10],
            "open_questions": open_questions,
        }

    logger.info("Session started", extra={"session_id": session_id, "project": project})

    return {
        "session_id": session_id,
        "project": project,
        "identity": identity,
        "directives": {
            "permanent": permanent,
            "project": project_directives,
            "domains": domain_directives,
        },
        "recent_sessions": session_summaries,
        "high_salience_memories": salient_memories,
        "pending_directive_changes": pending_changes,
        "pending_captures_processed": captured_count,
        "last_journal": last_journal_context,
    }


@mcp.tool()
def loom_session_end(
    summary: str,
    learnings: list[str] | str | None = None,
    surprises: list[str] | str | None = None,
    tags: list[str] | str | None = None,
    project: str | None = None,
) -> dict:
    """Close the current session: write notes, store memory, flag if journal is due.

    IMPORTANT: Call this only from the main Claude Code session. Sub-agents
    (Explore, Plan, Bash, general-purpose, etc.) must never call this tool.

    Args:
        summary: A brief summary of what was accomplished.
        learnings: Key insights or patterns discovered.
        surprises: Unexpected findings or challenges.
        tags: Tags for categorizing this session.
        project: Optional project name (ignored if a session is already active).
    """
    learnings = _coerce_list(learnings)
    surprises = _coerce_list(surprises)
    tags = _coerce_list(tags)

    # Find the active session (use the most recent one)
    if not _active_sessions:
        return {"error": "No active session. Call loom_session_start first."}

    project = next(reversed(_active_sessions))
    session = _active_sessions.pop(project)
    (ACTIVE_SESSIONS_DIR / project).unlink(missing_ok=True)
    session.ended_at = datetime.now()
    session.summary = summary
    session.learnings = learnings
    session.surprises = surprises
    session.tags = tags

    # Track domains from tags
    domain_tags = {
        "python", "typescript", "rust", "go",
        "java", "javascript", "react", "django",
    }
    detected_domains = set(tags) & domain_tags
    if detected_domains:
        _project_domains.setdefault(project, set()).update(detected_domains)

    # Write session file
    filepath = write_session_file(
        project=project,
        summary=summary,
        learnings=learnings,
        surprises=surprises,
        tags=tags,
        started_at=session.started_at,
    )
    session.file_path = str(filepath)

    # Store session in DB
    store_session(session)

    # Check if journal is due: 3+ sessions since the last journal/reflect
    recent = get_recent_sessions(project, limit=20)
    last_journal = get_latest_journal(project)
    if last_journal:
        sessions_since = sum(1 for s in recent if s.started_at > last_journal.created_at)
    else:
        sessions_since = len(recent)
    journal_due = sessions_since >= 3

    logger.info("Session ended", extra={"session_id": session.id, "project": project})

    return {
        "session_id": session.id,
        "project": project,
        "file_path": str(filepath),
        "journal_due": journal_due,
        "journal_hint": (
            f"{sessions_since} sessions since last reflect."
            " Consider running loom_reflect to synthesize."
            if journal_due
            else None
        ),
        "clear_hint": "Session stored. Run /clear to free up context for your next task.",
    }


@mcp.tool()
def loom_recall(
    query: str,
    project: str | None = None,
    memory_type: str | None = None,
    limit: int = 5,
) -> dict:
    """Semantic search over all memories.

    Args:
        query: Natural language search query.
        project: Optional project filter.
        memory_type: Optional type filter (indexed, session,
            journal, reconsolidated_insight).
        limit: Maximum results to return (default 5).
    """
    results = search_memories(
        query=query,
        project=project,
        memory_type=memory_type,
        limit=limit,
    )

    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "content": r.memory.content,
                "type": r.memory.memory_type,
                "project": r.memory.project,
                "similarity": round(r.similarity, 3),
                "salience": round(r.memory.salience, 2),
                "tags": r.memory.tags,
                "created_at": r.memory.created_at.isoformat(),
                "access_count": r.memory.access_count,
            }
            for r in results
        ],
    }


@mcp.tool()
def loom_remember(
    content: str,
    memory_type: str,
    project: str | None = None,
    tags: list[str] | str | None = None,
    salience: float = 0.5,
) -> dict:
    """Store a new memory mid-session.

    Args:
        content: The memory content to store.
        memory_type: Category (indexed, pattern, decision, insight).
        project: Optional project scope.
        tags: Optional tags for categorization.
        salience: Initial importance score 0.0–1.0 (default 0.5).
            Use 0.85+ for mistakes and hard-won lessons — ensures
            The Critic sees them prominently at reflect time.
    """
    memory_id = store_memory(
        content=content,
        memory_type=memory_type,
        project=project,
        tags=_coerce_list(tags),
        salience=salience,
    )

    return {
        "memory_id": memory_id,
        "stored": True,
        "content_preview": content[:100] + ("..." if len(content) > 100 else ""),
    }


@mcp.tool()
def loom_propose_directive(
    content: str,
    reasoning: str,
    file: str = "permanent.md",
) -> dict:
    """Immediately queue a directive proposal without running full reflect.

    Use this mid-session when you observe a mistake, anti-pattern, or
    hard-won lesson that should become a permanent rule. The proposal lands
    in the loom-approve queue right away — no need to wait for the weekly
    reflect cycle.

    Args:
        content: The directive text to add (written as an actionable rule,
            e.g. 'Never call X without Y — causes Z').
        reasoning: Why this rule is needed; cite the concrete error observed.
        file: Target directive file (default 'permanent.md').
            Use 'by-project/<name>.md' for project-specific rules,
            'by-domain/python.md' etc for language-specific rules.
    """
    # Semantic dedup: skip if a similar rule already exists in the target file.
    # Avoids directive file bloat from rephrased versions of existing rules.
    similar = find_similar_directive(content, file)
    if similar:
        return {
            "skipped": True,
            "reason": "Semantically similar rule already exists in target file.",
            "existing_rule": similar[:300],
            "hint": (
                "The existing rule covers this. Use loom_remember(salience=0.85) "
                "to log it as a high-priority memory instead, or target a different file."
            ),
        }

    change = DirectiveChange(
        id=_gen_id(),
        directive_file=file,
        change_type="add",
        proposed_diff=f"APPEND: {content}",
        reasoning=reasoning,
        source_reflection_id="manual",
    )
    store_directive_change(change)

    return {
        "change_id": change.id,
        "file": file,
        "status": "pending",
        "hint": "Run loom-approve to review and apply.",
    }


@mcp.tool()
def loom_directives(
    domain: str | None = None,
    project: str | None = None,
) -> dict:
    """Get active directives for the current context.

    Args:
        domain: Optional domain (python, typescript, etc.).
        project: Optional project name.
    """
    result: dict[str, str] = {}

    permanent = read_permanent_directives()
    if permanent:
        result["permanent"] = permanent

    if domain:
        domain_content = read_domain_directives(domain)
        if domain_content:
            result[f"domain_{domain}"] = domain_content

    if project:
        project_content = read_project_directives(project)
        if project_content:
            result[f"project_{project}"] = project_content

    return {"directives": result, "count": len(result)}


@mcp.tool()
def loom_reflect(
    days: int = 7,
    project: str | None = None,
    mode: str = "full",
    auto_approve: bool = False,
) -> dict:
    """Trigger the reflect cycle: journal synthesis, directive proposals, reconsolidation.

    Args:
        days: Number of days to look back (default 7).
        project: Optional project filter. If None, reflects across all projects.
        mode: Reflection mode - 'full' (all steps),
            'journal' (synthesis only),
            'directives' (proposals only).
        auto_approve: If True, automatically apply all proposed directive changes
            without requiring manual loom_approve calls, then run a dedup pass
            on each modified file.
    """
    from loom_mcp.reflection import run_reflection

    return run_reflection(days=days, project=project, mode=mode, auto_approve=auto_approve)


@mcp.tool()
def loom_approve(change_id: str, decision: str) -> dict:
    """Approve or reject a directive change proposal.

    Args:
        change_id: The ID of the directive change to resolve.
        decision: Either 'approve' or 'reject'.
    """
    if decision not in ("approve", "reject"):
        return {"error": "Decision must be 'approve' or 'reject'."}

    change = get_directive_change(change_id)
    if not change:
        return {"error": f"Directive change '{change_id}' not found."}

    if change.status != "pending":
        return {"error": f"Change already resolved as '{change.status}'."}

    archived_count = 0
    if decision == "approve":
        apply_directive_diff(change.directive_file, change.proposed_diff)
        # Archive memories that are now encoded in this directive
        similar = search_memories(query=change.proposed_diff, limit=10, min_salience=0.3)
        to_archive = [r.memory.id for r in similar if r.similarity > 0.80]
        archived_count = archive_memories(to_archive)
        if archived_count:
            logger.info(
                "Archived memories encoded in approved directive",
                extra={"change_id": change_id, "archived_count": archived_count},
            )

    resolve_directive_change(change_id, decision + "d")  # "approved" or "rejected"

    logger.info(
        "Directive change resolved",
        extra={"change_id": change_id, "decision": decision},
    )

    return {
        "change_id": change_id,
        "decision": decision,
        "file": change.directive_file,
        "applied": decision == "approve",
        "archived_memories": archived_count,
    }


@mcp.tool()
def loom_status() -> dict:
    """Get system stats: memory counts, salience distribution, pending changes."""
    stats = get_memory_stats()

    # Add active session info
    active = [
        {"project": p, "started": s.started_at.isoformat()}
        for p, s in _active_sessions.items()
    ]
    stats["active_sessions"] = active  # type: ignore[assignment]

    return stats

