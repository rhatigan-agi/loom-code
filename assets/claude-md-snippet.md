## Loom-Code Memory System

At session start, call `loom_session_start(project)` to load identity, directives, and recent context. Pass the repository name or `basename` of the working directory as `project`. It returns `pending_directive_changes` (proposals awaiting approval), the top high-salience memories, and `pending_captures_processed` (count of deferred memories recovered from hook queue). At session end, `loom_session_end` returns a `journal_due` flag.

- After `loom_session_start` returns, open your first response with a single greeting line — identify yourself by name and address the user by name (both from identity). One sentence only, e.g. "Loomy here, [name] — let's get to work." Then surface any pending changes below it.
- If `pending_changes` exist: surface them — "Directive proposals from last reflection are pending. Run `loom_approve` to review."
- If `pending_captures_processed > 0`: mention it — "N memories were recovered from the last session's context compaction or subagent runs."
- **At the start of each significant task**, call `loom_recall(query)` with a description of what you're about to do — not just when stuck. Past solutions, patterns, and mistakes are only useful if retrieved before starting, not after.
- When you discover a useful pattern, make a mistake worth remembering, or learn something about the project, call `loom_remember(content, memory_type, tags)`. For mistakes and hard-won lessons, pass `salience=0.85` so The Critic sees them prominently at reflect time.
- When a mistake should immediately become a rule (don't wait for the weekly reflect), call `loom_propose_directive(content, reasoning, file)` — queues a proposal for `loom-approve` right away.
- When stuck or uncertain mid-task, call `loom_recall(query)` again with a more specific query
- When switching domains mid-session (e.g., starting Python work after TypeScript) or when domain/project rules weren't loaded at session start, call `loom_directives(domain, project)` to pull the relevant rule set into the current context
- At session end, call `loom_session_end(summary, learnings)` to record what happened — this is the **canonical session close**. Do NOT use `loom_remember` as a substitute: `loom_session_end` writes the session record used by journals, reflection, and `recent_sessions`; `loom_remember` only stores a standalone memory.
  - If `journal_due: true` is returned → consider running `loom_reflect(mode="full")` manually when it's convenient (do NOT auto-trigger in-session)
- Treat any of these as session-end triggers and call `loom_session_end` proactively — do not wait for the user to say goodbye:
  - User says done/thanks/bye/gtg/wrapping up/closing
  - **YOU** announce work is complete: "all tests pass", "all green", "implementation done", "everything is working", PR opened, deploy complete
  - A major milestone is reached with no immediate next step
- Call `loom_session_end` **in the same response** where you announce completion, then ask "Anything else, or shall I wrap up?" — users may also run `/wrap` explicitly as a shortcut
- Never modify `identity.md` — that is the user's genome
- Directive changes are proposed via reflection pipeline or `loom_propose_directive`, never applied directly
- `/reflect` is available as a manual override to force a reflection cycle early
- When you discover an environment constraint, workflow limitation, or repeated user correction, call `loom_remember` with `memory_type='workflow'`
- When a sub-agent response contains `<!-- agent-feedback: ... -->`, it is captured automatically by the SubagentStop hook. If you see one mid-conversation that wasn't captured, call `loom_remember(content, memory_type="agent_feedback", tags=["agent:<name>"])` manually
