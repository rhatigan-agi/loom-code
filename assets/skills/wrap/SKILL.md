# /wrap — Close the Current Session

The user (or you, proactively) has invoked `/wrap` to close the active loom-code session and persist
what was learned. Follow these steps exactly.

---

## Step 1: Gather session context

Briefly review the conversation to identify:
- What was built, fixed, or decided
- Key technical decisions or constraints discovered
- Anything that surprised you or went differently than expected
- Domain tags that apply (python, typescript, react, django, etc.)

Do not ask the user to summarize — infer from the conversation. If the conversation is genuinely
ambiguous, write a one-sentence summary of your best interpretation.

---

## Step 2: Call loom_session_end

Call `loom_session_end` with:
- `summary`: 1–3 sentences covering what was accomplished
- `learnings`: list of specific, reusable insights (patterns, constraints, gotchas discovered)
- `surprises`: anything unexpected — failures, edge cases, architecture surprises (optional)
- `tags`: domain tags inferred from the work (e.g. `["python", "typescript", "tests"]`)

**This is the canonical session close.** Do not call `loom_remember` instead of or in addition to
`loom_session_end` for the session summary — `loom_session_end` writes the session record,
`loom_remember` only writes a standalone memory.

---

## Step 3: Report outcome

After `loom_session_end` returns, respond with a single brief confirmation:

> Session saved. [1-sentence summary of what was recorded.]

If `journal_due: true` is returned, add:

> Journal is due — run `/reflect` when you're ready to synthesize recent sessions.

---

## Step 4: Do not close prematurely

Only call `loom_session_end` if the work described in this conversation appears complete or
clearly paused with no immediate next step. If there are active open tasks or the user has
indicated they want to continue, do not wrap — respond and keep the session open.

---

## Notes

- `/wrap` is safe to call multiple times — `loom_session_end` is idempotent within a project scope
- If no active session exists (loom_session_start was never called), note this and skip step 2
- The skill is intentionally lightweight — no planning mode, no artifacts, no confirmation gate
