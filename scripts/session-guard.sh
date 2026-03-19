#!/usr/bin/env bash
# loom-code session guard — SessionStart hook.
#
# Reads cwd from the hook's stdin JSON, derives the project name from it,
# and checks for a per-project sentinel file. If none exists, outputs a
# reminder that gets injected into the conversation so Claude calls
# loom_session_start before doing anything else.
#
# Also checks for active or incomplete /loom work folders in the project
# and surfaces a one-line notice so Claude can inform the user at session open.
#
# Installed by install.sh as a SessionStart hook in ~/.claude/settings.json.
# Fires once per conversation open (not on every prompt).
# Each project gets its own sentinel: ~/.loom-code/.active_sessions/<project>

SENTINEL_DIR="${LOOM_HOME:-$HOME/.loom-code}/.active_sessions"
# Sentinels older than this are treated as orphaned (previous session never closed).
STALE_HOURS=2

# Parse cwd from the JSON payload on stdin; derive project = basename(cwd).
# If parsing fails for any reason, fall through to the reminder (safe side).
CWD=$(python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('cwd', ''))
except Exception:
    pass
" 2>/dev/null)

PROJECT=$(basename "${CWD:-}")

SENTINEL="$SENTINEL_DIR/$PROJECT"

# Determine session state:
#   no_sentinel  → no session was ever started (or was cleanly closed)
#   fresh        → sentinel is recent; session may be active in current conversation
#   stale        → sentinel is old; previous session was orphaned (never closed)
SESSION_STATE="no_sentinel"
if [ -f "$SENTINEL" ]; then
    NOW=$(date +%s)
    if [[ "$(uname)" == "Darwin" ]]; then
        MTIME=$(stat -f "%m" "$SENTINEL" 2>/dev/null || echo "$NOW")
    else
        MTIME=$(stat -c "%Y" "$SENTINEL" 2>/dev/null || echo "$NOW")
    fi
    AGE_HOURS=$(( (NOW - MTIME) / 3600 ))
    if [ "$AGE_HOURS" -ge "$STALE_HOURS" ]; then
        SESSION_STATE="stale"
    else
        SESSION_STATE="fresh"
    fi
fi

if [ "$SESSION_STATE" = "no_sentinel" ]; then
    if [ -n "$PROJECT" ]; then
        printf '[loom-code] No active session for project "%s". Call loom_session_start("%s") as your very first action — before reading files, before responding, before anything else.' "$PROJECT" "$PROJECT"
    else
        printf '[loom-code] No active session detected. Call loom_session_start("<project>") as your very first action — before reading files, before responding, before anything else.'
    fi
elif [ "$SESSION_STATE" = "stale" ]; then
    # Orphaned sentinel — previous session never called loom_session_end.
    # Prompt for a fresh session_start so the new conversation is properly tracked.
    if [ -n "$PROJECT" ]; then
        printf '[loom-code] Previous session for "%s" was not properly closed (orphaned). Call loom_session_start("%s") as your very first action to begin a new tracked session.' "$PROJECT" "$PROJECT"
    else
        printf '[loom-code] Orphaned session detected (previous session was not closed). Call loom_session_start("<project>") as your very first action.'
    fi
fi
# SESSION_STATE="fresh" → do nothing; session is active in this conversation.

# ── Loom work surface ──────────────────────────────────────────────────────────
# Check for active or incomplete /loom work folders in this project directory.
# Output is appended to the hook message (informational only, never blocks).
if [ -n "$CWD" ]; then
    python3 - "$CWD" 2>/dev/null <<'PYEOF'
import sys
from pathlib import Path

cwd = Path(sys.argv[1])
loom_dir = cwd / ".loom"
work_dir = loom_dir / "work"

if not work_dir.is_dir():
    sys.exit(0)

def has_incomplete_subtasks(status_path: Path) -> tuple[int, int]:
    """Return (checked, total) subtask counts. Returns (0,0) on parse error."""
    try:
        lines = status_path.read_text().splitlines()
        # Phase complete → skip entirely
        for line in lines:
            if line.strip().startswith("**Phase:**") and "complete" in line:
                return (0, 0)
        checked = sum(1 for l in lines if l.strip().startswith("- [x]"))
        total = sum(1 for l in lines if l.strip().startswith("- [x]") or l.strip().startswith("- [ ]"))
        return (checked, total)
    except Exception:
        return (0, 0)

# Check .loom/active first
active_file = loom_dir / "active"
active_slug = ""
if active_file.exists():
    active_slug = active_file.read_text().strip()

if active_slug:
    active_folder = work_dir / active_slug
    status_path = active_folder / "status.md"
    if active_folder.is_dir() and status_path.exists():
        checked, total = has_incomplete_subtasks(status_path)
        if total > 0 and checked < total:
            print(f"\n[loom] Active work: {active_slug} ({checked}/{total} subtasks complete). Run /loom-resume to continue.")
            sys.exit(0)

# No valid active — scan for incomplete folders
incomplete = []
for folder in sorted(work_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
    if not folder.is_dir():
        continue
    status_path = folder / "status.md"
    if not status_path.exists():
        continue
    checked, total = has_incomplete_subtasks(status_path)
    if total > 0 and checked < total:
        incomplete.append((folder.name, checked, total))

if len(incomplete) == 1:
    slug, checked, total = incomplete[0]
    print(f"\n[loom] Incomplete work: {slug} ({checked}/{total} subtasks). Run /loom-resume to continue.")
elif len(incomplete) > 1:
    print(f"\n[loom] {len(incomplete)} incomplete loom work folders found. Run /loom-resume to select one.")
PYEOF
fi
