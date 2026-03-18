# /reflect — loom-code Reflect Cycle

Trigger the loom-code reflection pipeline to synthesize recent sessions into journal entries, propose directive changes, and reconsolidate memories.

## Steps

1. Call `loom_reflect` with default parameters (days=7, mode=full) or with user-specified options.
2. Present the **journal entry** that was synthesized from recent sessions.
3. For each **directive proposal**:
   - Show the target file and change type
   - Show the proposed diff
   - Show the reasoning/evidence
   - Ask the user to approve or reject
4. Call `loom_approve(change_id, decision)` for each proposal based on user input.
5. Present any **reconsolidated insights** — cross-cutting patterns discovered across memories.
6. Show a summary of what happened: sessions analyzed, journal written, proposals made, memories decayed.

## Usage

```
/reflect                    # Full reflection, last 7 days, all projects
/reflect --days 14          # Look back 14 days
/reflect --project myapp    # Filter to specific project
/reflect --mode journal     # Journal synthesis only
/reflect --mode directives  # Directive proposals only
```

## Notes

- Requires LOOM_REFLECTION_API_KEY to be set (or configure via install.sh wizard)
- The reflection pipeline makes up to 3 LLM API calls (fewer in journal or directives mode)
- Directive changes are never auto-applied — they always require user approval
- identity.md is never modified by the system
