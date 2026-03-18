#!/usr/bin/env bash
# loom-code per-project bootstrap — run from any project root.
# Writes .claude/settings.json (quality hooks) and .claude/settings.local.json.
# MCP is registered at user scope by install.sh — no per-project .mcp.json needed.
set -euo pipefail

LOOM_SRC="$(dirname "$(readlink -f "$0")")"
LOOM_HOME="${LOOM_HOME:-$HOME/.loom-code}"

echo "=== loom-code Project Bootstrap ==="
echo "Project : $(pwd)"
echo ""

# ── Write .claude/settings.json with PostToolUse quality hooks ────────────────
CLAUDE_SETTINGS_DIR="$(pwd)/.claude"
CLAUDE_SETTINGS="$CLAUDE_SETTINGS_DIR/settings.json"
CLAUDE_SETTINGS_LOCAL="$CLAUDE_SETTINGS_DIR/settings.local.json"
QUALITY_CHECK="$LOOM_SRC/scripts/quality-check.sh"

mkdir -p "$CLAUDE_SETTINGS_DIR"

# settings.local.json must exist or Claude Code reports "invalid settings file"
if [ ! -f "$CLAUDE_SETTINGS_LOCAL" ]; then
    echo '{}' > "$CLAUDE_SETTINGS_LOCAL"
    echo "Created .claude/settings.local.json (required by Claude Code)."
fi

if [ ! -f "$CLAUDE_SETTINGS" ]; then
    cat > "$CLAUDE_SETTINGS" <<SETTINGS
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "$QUALITY_CHECK"
          }
        ]
      }
    ]
  }
}
SETTINGS
    echo "Created .claude/settings.json with PostToolUse quality hooks."
else
    # Fix if it still has the old invalid afterEdit format
    if grep -q "afterEdit" "$CLAUDE_SETTINGS" 2>/dev/null; then
        cat > "$CLAUDE_SETTINGS" <<SETTINGS
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "$QUALITY_CHECK"
          }
        ]
      }
    ]
  }
}
SETTINGS
        echo "Fixed .claude/settings.json (replaced invalid afterEdit with PostToolUse)."
    else
        echo ".claude/settings.json already exists, skipping."
    fi
fi

echo ""
echo "Done. Restart Claude Code to activate hooks."
