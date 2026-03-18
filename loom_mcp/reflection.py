"""loom-code reflection pipeline: The Reflect Cycle.

Three Codex patterns in one pipeline:
1. Journal Synthesis (The Memory Weaver)
2. Directive Proposals (The Critic)
3. Memory Reconsolidation
4. Entropy Decay
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from openai import OpenAI

from loom_mcp.config import (
    CRITIC_MODEL,
    DEFAULT_REFLECT_DAYS,
    RECONSOLIDATION_MODEL,
    REFLECTION_API_KEY,
    REFLECTION_BASE_URL,
    REFLECTION_MODEL,
    WEAVER_MODEL,
)
from loom_mcp.file_sync import (
    apply_directive_diff,
    dedup_directive_file,
    find_similar_directive,
    read_permanent_directives,
    write_journal_file,
)
from loom_mcp.memory import (
    _gen_id,
    archive_memories,
    decay_memories,
    get_high_salience_memories,
    get_recent_journals,
    get_sessions_since,
    resolve_directive_change,
    search_memories,
    store_directive_change,
    store_journal,
    store_memory,
    store_reflection,
)
from loom_mcp.models import DirectiveChange, Journal, Reflection

logger = logging.getLogger(__name__)


@dataclass
class InsightResult:
    """A reconsolidated insight with scope and lineage."""

    content: str
    project: str | None  # None = cross-project (global)
    captures_ids: list[str] = field(default_factory=list)  # source memory IDs
    supersedes_ids: list[str] = field(default_factory=list)  # obsolete insight IDs



def _call_claude(system: str, prompt: str, model: str = REFLECTION_MODEL) -> str:
    """Make a single LLM API call for reflection via the OpenAI-compatible SDK.

    Uses /v1/chat/completions — works with Anthropic's OpenAI-compat endpoint,
    Ollama (local), or any OpenAI-compatible endpoint.

    Override via env vars (or set during install):
      LOOM_REFLECTION_BASE_URL     — API base (without /v1; appended automatically)
      LOOM_REFLECTION_MODEL        — default model for all steps
      LOOM_WEAVER_MODEL            — override for journal synthesis step
      LOOM_CRITIC_MODEL            — override for directive proposals step
      LOOM_RECONSOLIDATION_MODEL   — override for reconsolidation step
      LOOM_REFLECTION_API_KEY      — key ("ollama" for local; real key for Anthropic)
    """
    base = REFLECTION_BASE_URL.rstrip("/")
    api_base = base if base.endswith("/v1") else f"{base}/v1"
    client = OpenAI(base_url=api_base, api_key=REFLECTION_API_KEY)
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or ""


def _synthesize_journal(
    project: str,
    sessions: list[dict],
) -> str:
    """Step 1: Journal Synthesis — The Memory Weaver.

    Args:
        project: The project name.
        sessions: List of session dicts with summary, learnings, surprises.

    Returns:
        The journal entry text.
    """
    session_text = "\n\n".join(
        f"### Session ({s['date']})\n"
        f"**Summary:** {s['summary']}\n"
        f"**Learnings:** {', '.join(s.get('learnings', []))}\n"
        f"**Surprises:** {', '.join(s.get('surprises', []))}"
        for s in sessions
    )

    today = datetime.now().strftime("%Y-%m-%d")
    project_list = project or "multiple"
    session_count = len(sessions)

    system = (
        "You are The Memory Weaver. You synthesize work sessions into reflective journal entries. "
        "Produce output in exactly this format:\n\n"
        "## Summary\n"
        f"**Date**: {today}  **Projects**: {project_list}  **Sessions**: {session_count}\n"
        "**Key Decisions**: [3-5 bullet points of major decisions made]\n"
        "**Patterns Identified**: [bullet points of recurring themes]\n"
        "**Open Questions / Unresolved**: [bullet points of unresolved issues]\n\n"
        "---\n\n"
        "[First-person narrative starting with 'As today...' or 'Today...' — "
        "write as the developer reflecting on their work. Capture the arc, "
        "challenges faced, and connections between sessions. Use narrative voice.]"
    )

    prompt = (
        f"Project: {project}\n\n"
        f"Sessions to synthesize:\n{session_text}\n\n"
        "Write the journal entry following the exact format specified. "
        "Use first person for the narrative section."
    )

    return _call_claude(system, prompt, model=WEAVER_MODEL)


def _consolidation_hint(current_directives: str) -> str:
    """Return consolidation instructions for The Critic based on directive file size.

    If the directive content has more than 60 bullet rules, prompts the Critic
    to look for consolidation opportunities and adds 'consolidate' as a valid
    change_type. Otherwise returns just the standard valid change_type line.
    """
    bullet_count = sum(
        1 for line in current_directives.splitlines() if line.strip().startswith("- ")
    )
    base = "Valid change_type values: 'add', 'modify', 'workflow', 'agent_update'"
    if bullet_count > 60:
        return (
            f"IMPORTANT — CONSOLIDATION NEEDED ({bullet_count} rules detected):\n"
            "The directive file is getting large. Scan for groups of related rules "
            "that can be merged into a single, more precise rule without losing coverage. "
            "If you find genuine consolidation opportunities, propose a change_type "
            "'consolidate' with a REPLACE: diff containing the full revised file content. "
            "Only consolidate if the result is strictly equivalent or stricter — never "
            "drop coverage. Do not consolidate just to reduce length.\n\n"
            + base
            + ", 'consolidate'."
        )
    return base + "."


def _propose_directives(
    project: str | None,
    current_directives: str,
    sessions: list[dict],
    journals: list[str],
    memories: list[dict],
) -> list[dict]:
    """Step 2: Directive Proposals — The Critic.

    Args:
        project: Optional project filter.
        current_directives: The current directive content.
        sessions: Recent session data.
        journals: Recent journal texts.
        memories: High-salience memory content.

    Returns:
        List of proposal dicts with file, change_type, diff, reasoning.
    """
    session_text = "\n".join(
        f"- ({s['date']}) {s['summary']}: learnings={s.get('learnings', [])}"
        for s in sessions
    )
    journal_text = "\n---\n".join(journals) if journals else "(no journals yet)"
    memory_text = "\n".join(
        f"- [{m['type']}] {m['content']} (salience: {m['salience']})"
        for m in memories
    )

    target_hint = (
        f"by-project/{project}.md" if project else "permanent.md or by-domain/*.md"
    )

    # Separate agent_feedback memories for explicit Critic attention
    agent_feedback_memories = [m for m in memories if m.get("type") == "agent_feedback"]
    agent_feedback_text = (
        "\n".join(
            f"- [agent:{m.get('tags', ['?'])[0] if m.get('tags') else '?'}] {m['content']}"
            for m in agent_feedback_memories
        )
        if agent_feedback_memories
        else "(none)"
    )

    system = (
        "You are The Critic. You analyze development patterns across sessions and "
        "propose evidence-based directive changes. Each proposal must:\n"
        "1. Cite evidence from multiple sessions\n"
        "2. Target a specific directive file\n"
        "3. Include the exact text to add or modify\n"
        "4. Explain why this pattern is worth encoding\n\n"
        "Rules:\n"
        "- Never touch identity.md\n"
        "- Prefer adding to existing files over creating new ones\n"
        "- Route project-specific rules to 'by-project/<project>.md', not permanent.md\n"
        "- Propose additions with 'APPEND:' prefix\n"
        "- Propose full-file replacements (consolidate only) with 'REPLACE:' prefix\n"
        "- Be conservative — only propose what the evidence strongly supports\n"
        "- Return valid JSON array of proposals\n\n"
        "CRITICAL — FORMAT:\n"
        "All APPEND: content must be formatted as `- ` bullet points. Never use `### ` "
        "section headers, 'Evidence:' blocks, or prose paragraphs as directive rules. "
        "Each rule must be a single self-contained `- ` bullet that includes all necessary "
        "context inline. For consolidate change_type, use REPLACE: with the full revised "
        "file content (all rules as `- ` bullets). Never use 'CONSOLIDATE:' as a diff prefix.\n\n"
        "CRITICAL — DEDUPLICATION:\n"
        "Before proposing any APPEND:, do an explicit check: scan the Current Directives "
        "section for key phrases from your proposed content. If any existing bullet covers "
        "the same principle — even with different wording, structure, or level of detail — "
        "do NOT propose it. This includes: section headers you would duplicate, bullets "
        "that overlap in concept, and rules that are subsets of existing rules. "
        "Proposing content already in the directives wastes review time and is a failure mode. "
        "When uncertain, skip the proposal — only add what is genuinely absent.\n\n"
        "IMPORTANT — HUNT FOR WORKFLOW PATTERNS:\n"
        "Actively look for 'workflow' category signals: environment constraints "
        "(e.g., cannot run X locally, tool limitations, devcontainer constraints), "
        "repeated user corrections (user always cancels X and asks for Y instead), "
        "and tool interaction patterns. Route these to permanent.md under a "
        "'## Workflow & Environment Constraints' section. "
        "Use change_type 'workflow' for these proposals.\n\n"
        "IMPORTANT — AGENT/SKILL SELF-IMPROVEMENT:\n"
        "Check the 'Agent Feedback' section below for structured feedback captured "
        "from agent runs. Each item was written by an agent in a <!-- agent-feedback: ... --> "
        "comment and captured by the session. If patterns emerge (e.g., the code-reviewer "
        "agent consistently misses a check that multiple sessions have requested), propose "
        "a targeted update to the agent or skill file. Use file paths like "
        "'agents/code-reviewer.md', 'agents/git-helper.md', 'agents/doc-writer.md', "
        "or 'skills/reflect/SKILL.md'. Use change_type 'agent_update' for these. "
        "Be conservative — only propose if the feedback is clear and consistent across "
        "multiple sessions, not from a single instance.\n\n"
        + _consolidation_hint(current_directives)
    )

    prompt = (
        f"## Current Directives\n{current_directives}\n\n"
        f"## Recent Sessions\n{session_text}\n\n"
        f"## Recent Journals\n{journal_text}\n\n"
        f"## High-Salience Memories\n{memory_text}\n\n"
        f"## Agent Feedback\n{agent_feedback_text}\n\n"
        f"Target files: {target_hint}\n\n"
        "Return a JSON array of directive change proposals. Each object should have:\n"
        '- "file": relative path — e.g. "permanent.md", "by-domain/python.md", '
        '"agents/code-reviewer.md", "skills/reflect/SKILL.md"\n'
        '- "change_type": "add", "modify", "workflow", "agent_update", or "consolidate"\n'
        '- "diff": the content change (prefix with APPEND: or REPLACE:)\n'
        '- "reasoning": evidence-based justification\n\n'
        "If no changes are warranted, return an empty array [].\n"
        "Return ONLY the JSON array, no markdown fencing."
    )

    raw = _call_claude(system, prompt, model=CRITIC_MODEL)

    # Parse JSON from response (handle potential markdown fencing)
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])

    # Fallback regex extraction for models that wrap JSON in prose
    import re
    if not text.startswith("["):
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            text = match.group(0)

    try:
        proposals = json.loads(text)
        if not isinstance(proposals, list):
            return []
    except json.JSONDecodeError:
        logger.warning("Failed to parse directive proposals", extra={"raw": raw[:200]})
        return []

    # Post-generation dedup: filter proposals whose content is already in the
    # target directive file. The Critic is instructed not to re-propose existing
    # rules, but LLMs miss this. Catch it here before polluting the approval queue.
    _additive_types = {"add", "workflow", "agent_update"}
    filtered: list[dict] = []
    for proposal in proposals:
        change_type = proposal.get("change_type", "add")
        diff = proposal.get("diff", "")
        directive_file = proposal.get("file", "permanent.md")

        if change_type in _additive_types and diff.startswith("APPEND:"):
            addition = diff[len("APPEND:"):].strip()
            similar = find_similar_directive(addition, directive_file)
            if similar:
                logger.info(
                    "Skipping duplicate proposal — content already in directives",
                    extra={"file": directive_file, "similar": similar[:80]},
                )
                continue

        filtered.append(proposal)

    return filtered


def _reconsolidate_memories(
    memories: list[dict],
    sessions: list[dict],
) -> tuple[list[InsightResult], list[str]]:
    """Step 3: Memory Reconsolidation.

    Args:
        memories: High-salience memories (must include 'id' and 'project' keys).
        sessions: Recent session data.

    Returns:
        Tuple of (insights, global_supersede_ids) where insights is a list of
        InsightResult objects and global_supersede_ids is a list of existing
        insight IDs now considered obsolete.
    """
    if not memories:
        return [], []

    import re

    # Fetch ALL existing reconsolidated insights to prevent re-creation
    existing_insights = get_high_salience_memories(
        project=None,
        threshold=0.0,
        limit=60,
        memory_type="reconsolidated_insight",
    )
    existing_text = (
        "\n".join(f"- [id:{m.id}] {m.content}" for m in existing_insights)
        if existing_insights
        else "(none yet)"
    )

    memory_text = "\n".join(
        f"- [id:{m['id']}] [{m['type']}] {m['content']} "
        f"(salience: {m['salience']}, tags: {m.get('tags', [])})"
        for m in memories
    )
    session_text = "\n".join(
        f"- ({s['date']}) {s['summary']}"
        for s in sessions
    )

    system = (
        "You are The Reconsolidator. You find cross-cutting insights that connect "
        "disparate memories and recent experiences. Your insights should reveal "
        "patterns, connections, or principles that aren't obvious from individual "
        "memories alone.\n\n"
        "CRITICAL — DEDUPLICATION:\n"
        "Review the EXISTING INSIGHTS carefully before generating anything. "
        "Do NOT recreate, rephrase, or generate variants of insights that are "
        "already there. Only produce genuinely new cross-cutting patterns that "
        "are not already captured in any existing insight.\n\n"
        "For each insight, the response must include:\n"
        "- 'cross_project': true if it draws from memories of MULTIPLE different projects, "
        "false if all sources are from one project or are global memories\n"
        "- 'captures_ids': list of memory IDs (from [id:...] tags above) that this insight synthesizes\n\n"
        "In 'supersede', list IDs of EXISTING insights (from the existing list above) that are:\n"
        "- Directly contradicted by new understanding\n"
        "- Fully absorbed into a new, better insight\n"
        "- No longer accurate given recent changes\n"
        "Only supersede when clearly warranted — err on the side of keeping."
    )

    prompt = (
        f"## EXISTING INSIGHTS (do not recreate these)\n{existing_text}\n\n"
        f"## High-Salience Memories\n{memory_text}\n\n"
        f"## Recent Sessions\n{session_text}\n\n"
        "Find NEW connections between these memories and recent work that are NOT "
        "already covered by the existing insights. Each insight should:\n"
        "- Connect at least 2 different memories or a memory with recent work\n"
        "- State the insight as a principle or observation\n"
        "- Be actionable or informative for future work\n"
        "- NOT duplicate or rephrase any existing insight\n\n"
        "Return a JSON object with two keys:\n"
        '- "insights": array of objects each with "content" (string), "cross_project" (bool), '
        'and "captures_ids" (array of memory IDs from the list above)\n'
        '- "supersede": array of existing insight IDs that are now obsolete\n\n'
        "Return ONLY the JSON object, no markdown fencing. "
        'If no new insights emerge, return {"insights": [], "supersede": []}'
    )

    raw = _call_claude(system, prompt, model=RECONSOLIDATION_MODEL)

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])

    # Parse the object (with legacy array fallback for old models)
    raw_insights: list[dict] = []
    supersede_ids: list[str] = []

    if text.startswith("["):
        # Legacy fallback: treat as plain insight list (old model output)
        try:
            legacy = json.loads(text)
            raw_insights = [
                {"content": str(s), "cross_project": False, "captures_ids": []}
                for s in legacy
                if isinstance(s, str)
            ]
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse legacy insight array",
                extra={"raw": raw[:200]},
            )
            return [], []
    else:
        # Try object extraction with regex fallback for prose-wrapped responses
        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)
        try:
            parsed = json.loads(text)
            raw_insights = parsed.get("insights", [])
            supersede_ids = parsed.get("supersede", [])
            if not isinstance(raw_insights, list):
                raw_insights = []
            if not isinstance(supersede_ids, list):
                supersede_ids = []
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse reconsolidation response",
                extra={"raw": raw[:200]},
            )
            return [], []

    # Programmatic project inference per insight
    mem_by_id = {m["id"]: m for m in memories}
    result_insights: list[InsightResult] = []

    for raw_insight in raw_insights:
        if not isinstance(raw_insight, dict):
            continue
        content = raw_insight.get("content", "")
        if not content:
            continue

        captures = [str(mid) for mid in raw_insight.get("captures_ids", [])]
        cross = raw_insight.get("cross_project", False)

        project: str | None = None
        if not cross and captures:
            source_projects = {
                mem_by_id[mid]["project"]
                for mid in captures
                if mid in mem_by_id
            }
            named = {p for p in source_projects if p is not None}
            if len(named) == 1:
                project = named.pop()
            # If >1 project or all global → stay None (cross-project)

        result_insights.append(InsightResult(
            content=content,
            project=project,
            captures_ids=captures,
            supersedes_ids=[],
        ))

    # Post-generation dedup: skip any insight too similar to existing ones
    filtered: list[InsightResult] = []
    for insight in result_insights:
        similar = search_memories(
            query=insight.content,
            memory_type="reconsolidated_insight",
            limit=3,
        )
        if any(r.similarity > 0.85 for r in similar):
            logger.info(
                "Skipping duplicate insight",
                extra={"insight_preview": insight.content[:80]},
            )
            continue
        filtered.append(insight)

    return filtered, supersede_ids


def run_reflection(
    days: int = DEFAULT_REFLECT_DAYS,
    project: str | None = None,
    mode: str = "full",
    auto_approve: bool = False,
) -> dict:
    """Run the full reflect cycle.

    Args:
        days: Number of days to look back.
        project: Optional project filter.
        mode: 'full', 'journal', or 'directives'.
        auto_approve: If True, automatically apply all proposed directive changes
            and run a dedup pass on each affected file. No pending changes are left.

    Returns:
        Dict with journal, proposals, insights, and decay stats.
    """
    reflection_id = _gen_id()
    since = datetime.now() - timedelta(days=days)

    # Gather data
    all_sessions = get_sessions_since(project or "", since) if project else []
    if not project:
        # Gather across all projects — get all sessions from DB
        from loom_mcp.init_db import get_connection

        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT DISTINCT project FROM sessions WHERE started_at >= ?",
                (since.isoformat(),),
            ).fetchall()
            projects = [r["project"] for r in rows]
            for p in projects:
                all_sessions.extend(get_sessions_since(p, since))
        finally:
            conn.close()

    session_dicts = [
        {
            "date": s.started_at.isoformat(),
            "summary": s.summary,
            "learnings": s.learnings,
            "surprises": s.surprises,
        }
        for s in all_sessions
    ]

    if not session_dicts:
        return {
            "reflection_id": reflection_id,
            "status": "no_sessions",
            "message": f"No sessions found in the last {days} days.",
        }

    # Gather high-salience memories
    high_sal = get_high_salience_memories(project=project, threshold=0.5, limit=20)
    memory_dicts = [
        {
            "id": m.id,
            "content": m.content,
            "type": m.memory_type,
            "project": m.project,
            "salience": round(m.salience, 2),
            "tags": m.tags,
        }
        for m in high_sal
    ]

    # Gather recent journals (up to 3 for Critic context)
    recent_journals = get_recent_journals(project, limit=3) if project else []
    journal_texts: list[str] = [j.content for j in recent_journals]

    result: dict = {
        "reflection_id": reflection_id,
        "sessions_analyzed": len(session_dicts),
    }

    session_ids = [s.id for s in all_sessions]
    proposal_ids: list[str] = []

    # Step 1: Journal Synthesis
    if mode in ("full", "journal"):
        target_project = project or all_sessions[0].project
        journal_content = _synthesize_journal(target_project, session_dicts)

        journal = Journal(
            id=_gen_id(),
            project=target_project,
            content=journal_content,
            source_session_ids=session_ids,
        )

        filepath = write_journal_file(
            project=target_project,
            content=journal_content,
            created_at=journal.created_at,
        )
        journal.file_path = str(filepath)
        store_journal(journal)

        # Also store as a searchable memory — higher salience so journals surface
        # in loom_recall without a dedicated tool
        store_memory(
            content=journal_content,
            memory_type="journal",
            project=target_project,
            tags=["reflection", "journal"],
            source_ids=session_ids,
            salience=0.72,
        )

        result["journal"] = {
            "id": journal.id,
            "project": target_project,
            "content": journal_content,
            "file_path": str(filepath),
        }

    # Step 2: Directive Proposals
    if mode in ("full", "directives"):
        current_directives = read_permanent_directives()
        if project:
            from loom_mcp.file_sync import read_project_directives

            proj_dir = read_project_directives(project)
            if proj_dir:
                current_directives += f"\n\n## Project: {project}\n{proj_dir}"

        proposals = _propose_directives(
            project=project,
            current_directives=current_directives,
            sessions=session_dicts,
            journals=journal_texts,
            memories=memory_dicts,
        )

        stored_proposals: list[dict] = []
        affected_files: set[str] = set()

        for p in proposals:
            change = DirectiveChange(
                id=_gen_id(),
                directive_file=p.get("file", "permanent.md"),
                change_type=p.get("change_type", "add"),
                proposed_diff=p.get("diff", ""),
                reasoning=p.get("reasoning", ""),
                source_reflection_id=reflection_id,
            )
            store_directive_change(change)
            proposal_ids.append(change.id)

            proposal_entry = {
                "id": change.id,
                "file": change.directive_file,
                "type": change.change_type,
                "diff": change.proposed_diff,
                "reasoning": change.reasoning,
            }

            if auto_approve:
                apply_directive_diff(change.directive_file, change.proposed_diff)
                resolve_directive_change(change.id, "approved")
                affected_files.add(change.directive_file)
                proposal_entry["auto_approved"] = True

            stored_proposals.append(proposal_entry)

        # Post-apply dedup pass on all modified files
        if auto_approve and affected_files:
            dedup_stats: dict[str, int] = {}
            for directive_file in affected_files:
                removed = dedup_directive_file(directive_file)
                dedup_stats[directive_file] = removed
            result["dedup"] = dedup_stats

        result["proposals"] = stored_proposals

    # Step 3: Memory Reconsolidation
    if mode == "full" and memory_dicts:
        insights, supersede_ids = _reconsolidate_memories(memory_dicts, session_dicts)

        archived_source_count = 0
        for insight in insights:
            store_memory(
                content=insight.content,
                memory_type="reconsolidated_insight",
                project=insight.project,  # scoped or global
                tags=["reconsolidation", "insight"],
                source_ids=insight.captures_ids,  # precise lineage
                salience=0.7,
            )
            if insight.captures_ids:
                archived_source_count += archive_memories(insight.captures_ids)

        if supersede_ids:
            archive_memories(supersede_ids)

        result["insights"] = [i.content for i in insights]
        result["archived_sources"] = archived_source_count
        result["superseded"] = len(supersede_ids)

    # Step 4: Entropy Decay
    if mode == "full":
        decayed_count = decay_memories(days_threshold=days * 2)
        result["decay"] = {"memories_decayed": decayed_count}

    # Store the reflection record
    reflection = Reflection(
        id=reflection_id,
        trigger=f"manual:{mode}",
        sessions_analyzed=session_ids,
        journals_analyzed=[j.id for j in recent_journals],
        synthesis=result.get("journal", {}).get("content", ""),
        proposed_changes=proposal_ids,
    )
    store_reflection(reflection)

    result["status"] = "complete"
    return result
