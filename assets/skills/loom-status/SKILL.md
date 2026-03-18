# /loom-status — Show Loom Work State

Show the current state of loom work in this project. Do not start, modify, or resume any work.
This command is read-only.

---

## Step 1: Identify what to show

1. Check if `.loom/` exists in the current working directory. If not: *"No loom work folder found
   in this project. Run `/loom <description>` to start."* Stop here.

2. Read `.loom/active`. If it contains a valid slug and that folder exists → show that folder's
   full status (Step 2a).

3. If no valid active folder: scan `.loom/work/` for all folders and show a summary of each
   (Step 2b).

4. If `.loom/work/` is empty or does not exist: *"No work folders found. Run `/loom <description>`
   to start."* Stop here.

---

## Step 2a: Full status for the active folder

Read `spec.md`, `plan.md`, and `status.md`. Display:

```
Active: <slug>
Classification: moderate | substantial
Phase: plan | build | complete
Last Updated: <timestamp>

Subtasks:
  [x] 1. Task name
  [ ] 2. Task name
  [ ] 3. Task name

Blocked: <item — reason> | none
```

Also show the first unchecked subtask as: *"Next: <subtask name>"*

---

## Step 2b: Summary view (no active folder)

For each folder in `.loom/work/`, read its `status.md` and show one line per folder:

```
<slug>  <phase>  <N>/<total> subtasks  [complete | in progress | blocked]
```

Sort by Last Updated descending (most recently touched first).

---

## Notes

- Do not read or display the contents of `spec.md` or `plan.md` unless the user explicitly
  asks. Status is about progress, not scope.
- Do not modify any files.
- Do not call `EnterPlanMode` or begin any build work.
