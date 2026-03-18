#!/usr/bin/env bash
# loom-code quality check — wired as a PostToolUse hook in .claude/settings.json.
# Claude Code calls this after Edit/Write/MultiEdit, passing tool JSON on stdin.
# Runs the appropriate linter based on file extension. Silent on no match.
# Always exits 0 — linter violations are printed to stdout for Claude to read;
# they never block edits and never produce spurious stderr.

LOOM_HOME="${LOOM_HOME:-$HOME/.loom-code}"
VENV_RUFF="$LOOM_HOME/.venv/bin/ruff"

# Prefer venv ruff; fall back to system ruff if present.
if [ -x "$VENV_RUFF" ]; then
    RUFF="$VENV_RUFF"
elif command -v ruff &>/dev/null; then
    RUFF="$(command -v ruff)"
else
    RUFF=""
fi

# Extract file_path from the PostToolUse JSON payload on stdin.
FILE_PATH="$(python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")"

[ -z "$FILE_PATH" ] && exit 0
[ ! -f "$FILE_PATH" ] && exit 0

case "$FILE_PATH" in
    *.ts|*.tsx)
        ROOT="$(dirname "$(realpath "$FILE_PATH")")"
        while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/tsconfig.json" ]; do
            ROOT="$(dirname "$ROOT")"
        done
        if [ -f "$ROOT/tsconfig.json" ]; then
            cd "$ROOT" && npx tsc --noEmit --pretty 2>&1 | head -20 || true
        fi
        ;;
    *.py)
        if [ -n "$RUFF" ]; then
            "$RUFF" check --select E,F,I --quiet "$FILE_PATH" 2>&1 | head -20 || true
        fi
        ;;
    *.js|*.jsx)
        ROOT="$(dirname "$(realpath "$FILE_PATH")")"
        while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/package.json" ]; do
            ROOT="$(dirname "$ROOT")"
        done
        if [ -f "$ROOT/package.json" ]; then
            cd "$ROOT" && npx eslint --quiet "$FILE_PATH" 2>&1 | head -20 || true
        fi
        ;;
esac

exit 0
