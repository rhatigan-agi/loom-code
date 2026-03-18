#!/usr/bin/env bash
# loom-code SubagentStop hook — auto-captures agent-feedback from subagent output.
# Claude Code fires this when a subagent finishes. Scans output for
# <!-- agent-feedback: agent-name: content --> comments and queues them
# as memories — no manual loom_remember call required.
#
# Installed by install.sh as a SubagentStop hook in ~/.claude/settings.json.

LOOM_HOME="${LOOM_HOME:-$HOME/.loom-code}"
SCRIPT="$LOOM_HOME/scripts/subagent-stop-capture.py"

[ -f "$SCRIPT" ] || exit 0

exec python3 "$SCRIPT"
