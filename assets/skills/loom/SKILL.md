# /loom — Artifact-Driven Development Pipeline

The user has invoked `/loom` with a task description. This may be a single sentence, a paragraph,
or a pasted GitHub issue. Follow these steps exactly.

---

## Step 1: Classify the task

Read the full description carefully. Classify as one of three tiers. Use these signals — all four
must hold for **trivial**; anything else routes to **moderate** or **substantial**.

**Trivial** — ALL of these must be true:
- Tightly scoped (one file, or a very small number of related lines)
- Low ambiguity (the correct implementation is clear without further discussion)
- Low coordination cost (no interface changes, no cross-module concerns, no seams to define)
- Reversible (easy to undo or adjust direction)

**Moderate** — not trivial, AND:
- Requirements are clear enough to decompose into ordered tasks
- Affects a bounded set of files (roughly 2–8)
- Unknowns are resolvable by reasonable assumption

**Substantial** — any of:
- Requirements are ambiguous, involve multiple concerns, or span many modules
- The description is a pasted GitHub issue or a paragraph with open questions
- More than ~5 unknowns that cannot be safely assumed
- The work would span multiple sessions or require defining explicit seams between components

---

## Step 2: Check for active work

Check whether `.loom/active` exists in the current working directory.

If it exists and contains a non-empty slug:
- Warn the user inline: *"Active loom work exists: `<slug>`. Start a new task anyway, or run
  `/loom-resume` to continue?"*
- Wait for confirmation before proceeding.

---

## Step 3: Execute the appropriate path

### Trivial path

Output a single inline line describing what you are about to do. Do not enter planning mode.
Do not create any artifacts. Begin immediately.

---

### Moderate path

1. Call `EnterPlanMode`.

2. Draft the contents of `spec.md` and `plan.md` (see schemas below).

3. Before calling `ExitPlanMode`: if any information is **genuinely unknowable** from the
   description AND would materially change the spec or plan, call `AskUserQuestion` (max 2
   questions). Otherwise make a reasonable assumption and record it in the Assumptions section
   of `spec.md`. Do not ask questions that can be answered by assumption.

4. Present the spec and plan clearly. Call `ExitPlanMode`.

5. On user approval:
   - Generate a slug: `YYYYMMDD-<kebab-summary-of-task>` (e.g. `20260318-stripe-webhook`)
   - Create `.loom/README.md` if it does not already exist (see content below)
   - Create `.loom/work/<slug>/` and write `spec.md`, `plan.md`, `status.md`
   - Write the slug to `.loom/active`

6. Build sequentially. After each task completes:
   - Validate it (per the Validation field in plan.md)
   - Update `status.md`: check off the completed task, update Last Updated timestamp
   - Do not proceed to the next task if validation fails

---

### Substantial path

1. Call `EnterPlanMode`.

2. Draft the contents of `spec.md` (see schema below).

3. Run an inline critic pass on the spec — re-read it and check for:
   - Missing edge cases not covered by acceptance criteria
   - Acceptance criteria that are ambiguous or untestable
   - Hidden migration or backward-compatibility concerns
   - Unstated non-goals that could cause scope creep
   Fold any findings back into `spec.md` (as constraints, non-goals, or open questions).
   Do not surface the critic pass as separate output — integrate findings silently.

4. Draft the contents of `plan.md` (substantial format — see schema below).

5. Before calling `ExitPlanMode`: if any information is genuinely unknowable, call
   `AskUserQuestion` (max 3 questions). Otherwise assume and record.

6. Present spec and plan clearly. Call `ExitPlanMode`.

7. On user approval:
   - Generate a slug: `YYYYMMDD-<kebab-summary-of-task>`
   - Create `.loom/README.md` if it does not already exist
   - Create `.loom/work/<slug>/` and write `spec.md`, `plan.md`, `status.md`, `decisions.md`
   - Write the slug to `.loom/active`

8. Build sequentially. After each subtask completes:
   - Validate it (per the Proof/Test field in plan.md)
   - Update `status.md`: check off the completed subtask, update Last Updated timestamp
   - If a decision was made during build that was not already in the spec, append it to
     `decisions.md`
   - Do not proceed to the next subtask if validation fails

---

## Work Folder Structure

```
.loom/
  README.md          ← two-line attribution, created once
  active             ← current slug (plain text), or empty
  work/
    <slug>/
      spec.md
      plan.md
      status.md
      decisions.md   ← substantial path only
```

### `.loom/README.md` content (create only if file does not exist):

```
Work artifacts managed by loom-code.
https://github.com/rhatigan/loom-code
```

---

## File Schemas

### `spec.md` (moderate and substantial)

```markdown
# Problem Statement

# Acceptance Criteria
- [ ] ...

# Constraints

# Non-Goals

# Assumptions
<!-- What was inferred rather than asked. Record every assumption here. -->

# Open Questions
<!-- Only what cannot proceed without an answer. Resolved via AskUserQuestion before ExitPlanMode. -->
```

---

### `plan.md` — moderate

```markdown
# Affected Files / Modules

# Tasks
- [ ] 1. Task name
  - Files: ...
  - Validation: ...
- [ ] 2. ...
```

---

### `plan.md` — substantial

```markdown
# Subtasks

## 1. Subtask Name
- **Goal:**
- **Files / Modules:**
- **Interface / Contract:**
- **Proof / Test:**
- **Dependencies:** (prior subtask numbers, or "none")
- **Safe Partial State:** (what invariants hold if interrupted here)

## 2. ...
```

---

### `status.md` (all non-trivial paths)

```markdown
# Status

**Phase:** plan | build | complete
**Classification:** moderate | substantial
**Last Updated:** <ISO 8601 timestamp>

## Subtasks
- [ ] 1. Task name
- [x] 2. Task name

## Blocked
<!-- item — reason, or "none" -->
```

---

### `decisions.md` (substantial only, append-only during build)

```markdown
## <Short title> — <ISO 8601 timestamp>
**Context:**
**Options considered:**
**Choice and rationale:**
```

---

## Clearing `.loom/active`

Set `.loom/active` to empty (write an empty file, do not delete it) when:
- The Phase field in `status.md` is set to `complete`, OR
- All subtasks in `status.md` are checked

---

## Notes

- The `.loom/` folder is not gitignored by default. Teams may choose to commit it (collaborative
  artifact) or gitignore it (local scratchpad). A note to this effect is in `.loom/README.md`.
- Do not create `decisions.md` on the moderate path.
- The critic pass on the substantial path is silent — never say "now running critic pass."
- Never ask more questions than the caps above. Default is to assume and record.
