# /loom-resume — Resume Active Loom Work

Scan `.loom/work/` for incomplete work folders and resume the correct one. Follow these steps
exactly. Do not start new work — only resume existing work.

---

## Step 1: Determine which folder to resume

Apply these rules in order:

1. Read `.loom/active`. If it contains a valid slug AND that folder exists AND its `status.md`
   has at least one unchecked subtask → **resume it directly. No prompt.**

2. If `.loom/active` is missing, empty, or points to a folder that does not exist or is already
   complete: scan `.loom/work/` for all folders whose `status.md` has Phase not set to `complete`
   and at least one unchecked subtask.
   - If **exactly one** incomplete folder found → **resume it directly. No prompt.**
   - If **multiple** incomplete folders found → surface a selection list:
     - For each: show slug, classification, current phase, completion fraction (e.g. `3/7 subtasks`)
     - Call `AskUserQuestion` to let the user pick one
   - If **no** incomplete folders found → inform the user: "No incomplete loom work found in this
     project." Stop here.

3. Write the chosen slug to `.loom/active`.

---

## Step 2: Load context

Read `spec.md`, `plan.md`, and `status.md` from the selected folder.

If the substantial path is active, also read `decisions.md`.

Identify the first unchecked subtask in `status.md`.

---

## Step 3: Resume

State which work folder is active and which subtask is next. Then continue building from that
subtask using the same build rules as `/loom`:

- Validate each subtask before proceeding to the next
- Update `status.md` after each completed subtask (check it off, update Last Updated timestamp)
- Append to `decisions.md` if a decision was made that was not in the spec (substantial only)
- Do not skip subtasks with failed validation
- Clear `.loom/active` (write empty file) when all subtasks are complete and Phase is set to
  `complete`

---

## Notes

- Never modify `spec.md` or `plan.md` during resume. Those are locked after approval.
- If the user wants to change scope, they should update the files manually and note the change
  in `decisions.md`, then continue.
- If a subtask is blocked, mark it in the `## Blocked` section of `status.md` and move on only
  if the subtask has a `Safe Partial State` that permits it.
