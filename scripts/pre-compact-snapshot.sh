#!/usr/bin/env bash
# loom-code PreCompact hook — queues a working context snapshot before compaction.
# Claude Code fires this before compressing the context window.
# Uses a pending-captures queue (no embedding model cold-load in the hook).
# loom_session_start drains the queue at the next conversation open.
#
# Installed by install.sh as a PreCompact hook in ~/.claude/settings.json.

LOOM_HOME="${LOOM_HOME:-$HOME/.loom-code}"
SCRIPT="$LOOM_HOME/scripts/pre-compact-snapshot.py"

[ -f "$SCRIPT" ] || exit 0

exec python3 "$SCRIPT"
