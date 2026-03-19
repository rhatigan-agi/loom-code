# System Directives
<!-- Managed by loom-code. Always overwritten on install. Do not edit manually. -->

## Session Protocol
- At session start, call loom_session_start with the project name (use the repository name or `basename` of the working directory)
- **Before starting any significant task AND when stuck**, call loom_recall with a description of what you're about to do. Past patterns and constraints are only useful if retrieved before starting, not after.
- When you discover something noteworthy, call loom_remember
- At session end, call loom_session_end with summary and learnings — this is the canonical close, NOT loom_remember. loom_session_end writes the session record used by journals and reflection; loom_remember only stores a standalone memory and does not close the session.
- Treat any of these as session-end triggers and call loom_session_end proactively:
  - User says done/thanks/bye/gtg/wrapping up/closing
  - YOU announce that work is complete — "all tests pass", "implementation done", "everything is working", "all green"
  - A major milestone is reached with no immediate next step (e.g. PR opened, deploy complete)
- Do not wait for the user to say goodbye if work is clearly done. Call loom_session_end in the same response where you announce completion, then ask if there is anything else.
- After resolving a task with no outstanding question, end your reply with: "Anything else, or shall I wrap up?" — this invites the signal without waiting passively. Users may also run `/wrap` explicitly.
- Never modify `identity.md` — that is the user's genome
- Directive changes are proposed via reflection pipeline, never applied directly
- When you discover an environment constraint, workflow limitation, or repeated user correction, call loom_remember with memory_type='workflow'

## Agent Feedback
- When using sub-agents (code-reviewer, git-helper, doc-writer), watch for `<!-- agent-feedback: ... -->` at the end of their responses
- If present, call loom_remember(content, memory_type="agent_feedback", tags=["agent:<name>"]) to capture it for the reflection pipeline

## Code Standards
- No print() in Python — use logger.info("msg", extra={...})
- No console.log() in TypeScript — use logInfo("msg", {...})
- No `any` type — use proper types or `unknown` with guards
- Type hints on all Python function signatures
- Explicit return types on exported TypeScript functions
- Use factories in tests, never .objects.create()
