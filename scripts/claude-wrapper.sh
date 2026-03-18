#!/usr/bin/env bash
# loom-code claude wrapper — transparent drop-in for the claude binary.
#
# Passes all args through to the real claude binary unchanged.
# On any exit (clean, Ctrl-C, SIGTERM, or kill), closes any orphaned
# loom-code sessions so they don't get skipped by reflection.
#
# Installed by install.sh as: alias claude='...claude-wrapper.sh'

set -euo pipefail

LOOM_HOME="${LOOM_HOME:-$HOME/.loom-code}"
VENV_PYTHON="$LOOM_HOME/.venv/bin/python"

# ── Find real claude binary ───────────────────────────────────────────────────
# LOOM_REAL_CLAUDE is set at install time (absolute path, never the alias).
# Fallback: search PATH excluding this script's directory.
if [ -n "${LOOM_REAL_CLAUDE:-}" ] && [ -x "$LOOM_REAL_CLAUDE" ]; then
    REAL_CLAUDE="$LOOM_REAL_CLAUDE"
else
    # Find claude in PATH, skipping anything in our scripts dir
    SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
    REAL_CLAUDE="$(
        IFS=:
        for dir in $PATH; do
            [ "$dir" = "$SCRIPT_DIR" ] && continue
            [ -x "$dir/claude" ] && echo "$dir/claude" && break
        done
    )"
    if [ -z "$REAL_CLAUDE" ]; then
        echo "loom-code wrapper: cannot find claude binary. Set LOOM_REAL_CLAUDE." >&2
        exit 1
    fi
fi

# ── Orphan cleanup on any exit ────────────────────────────────────────────────
_cleanup() {
    if [ -x "$VENV_PYTHON" ] && [ -f "$LOOM_HOME/db/loom.db" ]; then
        "$VENV_PYTHON" -m loom_mcp.close_orphan 2>/dev/null || true
    fi
}
trap _cleanup EXIT

# ── Run real claude ───────────────────────────────────────────────────────────
# Do NOT use exec — we need the trap to fire on exit.
"$REAL_CLAUDE" "$@"
