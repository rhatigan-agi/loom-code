#!/usr/bin/env bash
# loom-code system install — idempotent, safe to re-run
# Detects its own location so it works from any machine after git clone.
set -euo pipefail

LOOM_SRC="$(dirname "$(readlink -f "$0")")"
LOOM_HOME="${LOOM_HOME:-$HOME/.loom-code}"
VENV="$LOOM_HOME/.venv"
UPDATE_MODE=false

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --update) UPDATE_MODE=true ;;
    esac
done

echo "=== loom-code Installer ==="
echo "Source : $LOOM_SRC"
echo "Runtime: $LOOM_HOME"
echo ""

# ── 1. Runtime directory tree ─────────────────────────────────────────────────
echo "[1/12] Creating runtime directory tree..."
mkdir -p "$LOOM_HOME"/{directives/by-domain,directives/by-project,sessions,journals,db,.model-cache,pending-captures}
echo "  Done."

# ── 2. Python virtual environment ─────────────────────────────────────────────
echo "[2/12] Setting up Python virtual environment..."

# Detect the best available Python >= 3.12
PYTHON_BIN=""
for candidate in python3.14 python3.13 python3.12 python3; do
    if command -v "$candidate" &>/dev/null; then
        PY_VERSION="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)"
        PY_MAJOR="${PY_VERSION%%.*}"
        PY_MINOR="${PY_VERSION##*.}"
        if [ "$PY_MAJOR" -ge 3 ] 2>/dev/null && [ "$PY_MINOR" -ge 12 ] 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "  ERROR: Python 3.12+ is required but not found."
    echo "  Install Python 3.12+ and re-run install.sh."
    exit 1
fi
echo "  Using $PYTHON_BIN (version $PY_VERSION)"

if [ ! -d "$VENV" ]; then
    "$PYTHON_BIN" -m venv "$VENV"
    echo "  Created new venv."
else
    echo "  Venv already exists, skipping creation."
fi

# ── 3. Editable install ───────────────────────────────────────────────────────
echo "[3/12] Installing loom-code as editable package..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$LOOM_SRC"
echo "  Done. Source is live — git pull = instant update, no reinstall needed."

# ── 4. Provider wizard ────────────────────────────────────────────────────────
ENV_FILE="$LOOM_HOME/.env"

if [ "$UPDATE_MODE" = true ] && [ -f "$ENV_FILE" ]; then
    echo "[4/12] Update mode: re-using existing config from $ENV_FILE"
    # Still update LOOM_SRC_PATH in case the source directory moved
    python3 - "$ENV_FILE" "$LOOM_SRC" <<'PYEOF'
import sys
from pathlib import Path
env_file, src = Path(sys.argv[1]), sys.argv[2]
lines = env_file.read_text().splitlines() if env_file.exists() else []
lines = [l for l in lines if not l.startswith("LOOM_SRC_PATH=")]
lines.append(f"LOOM_SRC_PATH={src}")
env_file.write_text("\n".join(lines) + "\n")
PYEOF
else
    echo "[4/12] Configuring loom-code..."
    echo ""
    read -r -p "  Your name (used in identity.md): " LOOM_USER_NAME
    LOOM_USER_NAME="${LOOM_USER_NAME:-Human}"
    echo ""
    echo "  [?] Which LLM provider for reflection?"
    echo "  1) Anthropic API  (claude-haiku-4-5-20251101 — recommended, needs API key)"
    echo "  2) Ollama          (local, needs Ollama running)"
    echo "  3) OpenAI-compatible endpoint"
    echo ""
    read -r -p "  Choice [1]: " PROVIDER_CHOICE
    PROVIDER_CHOICE="${PROVIDER_CHOICE:-1}"

    case "$PROVIDER_CHOICE" in
        1)
            read -r -p "  Anthropic API key: " LOOM_REFLECTION_API_KEY
            LOOM_REFLECTION_BASE_URL="https://api.anthropic.com"
            LOOM_REFLECTION_MODEL="claude-haiku-4-5-20251101"
            ;;
        2)
            read -r -p "  Ollama base URL [http://localhost:11434]: " LOOM_REFLECTION_BASE_URL
            LOOM_REFLECTION_BASE_URL="${LOOM_REFLECTION_BASE_URL:-http://localhost:11434}"
            # Ensure scheme is present
            case "$LOOM_REFLECTION_BASE_URL" in
                http://*|https://*) ;;
                *) LOOM_REFLECTION_BASE_URL="http://$LOOM_REFLECTION_BASE_URL" ;;
            esac
            read -r -p "  Model name [qwen3:8b]: " LOOM_REFLECTION_MODEL
            LOOM_REFLECTION_MODEL="${LOOM_REFLECTION_MODEL:-qwen3:8b}"
            LOOM_REFLECTION_API_KEY="ollama"
            ;;
        3)
            read -r -p "  Base URL: " LOOM_REFLECTION_BASE_URL
            read -r -p "  API key: " LOOM_REFLECTION_API_KEY
            read -r -p "  Model name: " LOOM_REFLECTION_MODEL
            ;;
        *)
            echo "  Invalid choice, defaulting to Anthropic."
            read -r -p "  Anthropic API key: " LOOM_REFLECTION_API_KEY
            LOOM_REFLECTION_BASE_URL="https://api.anthropic.com"
            LOOM_REFLECTION_MODEL="claude-haiku-4-5-20251101"
            ;;
    esac

    # Write .env file
    cat > "$ENV_FILE" <<ENVEOF
LOOM_USER_NAME=$LOOM_USER_NAME
LOOM_SRC_PATH=$LOOM_SRC
LOOM_REFLECTION_MODEL=$LOOM_REFLECTION_MODEL
LOOM_REFLECTION_BASE_URL=$LOOM_REFLECTION_BASE_URL
LOOM_REFLECTION_API_KEY=$LOOM_REFLECTION_API_KEY
ENVEOF
    chmod 600 "$ENV_FILE"
    echo "  Config written to $ENV_FILE"
fi

# Read LOOM_USER_NAME from .env for use in this script
LOOM_USER_NAME="$(python3 -c "
import re
try:
    m = re.search(r'^LOOM_USER_NAME=(.*)$', open('$ENV_FILE').read(), re.M)
    print(m.group(1).strip() if m else 'Human')
except: print('Human')
")"

# ── 5. Pre-download embedding model ───────────────────────────────────────────
echo "[5/12] Pre-downloading embedding model..."
"$VENV/bin/python" - <<PYEOF
from sentence_transformers import SentenceTransformer
import os
cache_dir = os.path.join("$LOOM_HOME", ".model-cache")
SentenceTransformer("all-MiniLM-L6-v2", cache_folder=cache_dir)
print("  Model ready at", cache_dir)
PYEOF

# ── 6. Initialize SQLite schema ───────────────────────────────────────────────
echo "[6/12] Initializing database..."
LOOM_HOME="$LOOM_HOME" "$VENV/bin/python" -m loom_mcp.init_db
echo "  Done."

# ── 7. Seed identity.md from template ─────────────────────────────────────────
echo "[7/12] Checking starter files..."
if [ ! -f "$LOOM_HOME/identity.md" ]; then
    python3 - "$LOOM_SRC/assets/identity.md.template" "$LOOM_HOME/identity.md" "$LOOM_USER_NAME" <<'PYEOF'
import sys
from pathlib import Path
template, dest, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
content = template.read_text().replace("{{USER_NAME}}", name)
dest.write_text(content)
PYEOF
    echo "  Created identity.md for $LOOM_USER_NAME."
else
    echo "  identity.md already exists, skipping."
fi

# ── 8. Seed directives/permanent.md from assets ───────────────────────────────
echo "[8/12] Seeding directives..."
if [ ! -f "$LOOM_HOME/directives/permanent.md" ]; then
    cp "$LOOM_SRC/assets/directives/permanent.md" "$LOOM_HOME/directives/permanent.md"
    echo "  Created directives/permanent.md from assets."
else
    echo "  directives/permanent.md already exists, skipping."
fi

# ── 9. Register MCP server at user scope ──────────────────────────────────────
echo "[9/12] Registering loom-code MCP server (user scope)..."
CLAUDE_BIN="$(command -v claude 2>/dev/null || echo "")"
if [ -z "$CLAUDE_BIN" ]; then
    echo "  WARNING: claude binary not found in PATH. Register manually after installing claude:"
    echo "  claude mcp add --scope user loom-code --env LOOM_HOME=\"\$LOOM_HOME\" $VENV/bin/python -- -m loom_mcp"
else
    if "$CLAUDE_BIN" mcp list 2>/dev/null | grep -q "^loom-code:"; then
        echo "  Already registered at user scope, skipping."
    else
        "$CLAUDE_BIN" mcp add --scope user loom-code \
            --env LOOM_HOME="$LOOM_HOME" \
            -- "$VENV/bin/python" -m loom_mcp
        echo "  Registered. loom-code is now available in all projects automatically."
    fi
fi

# ── 10. Install skills to ~/.claude/skills/ ───────────────────────────────────
echo "[10/12] Installing skills to ~/.claude/skills/..."
for skill_dir in "$LOOM_SRC/assets/skills/"*/; do
    [ -d "$skill_dir" ] || continue
    skill_name="$(basename "$skill_dir")"
    dest="$HOME/.claude/skills/$skill_name"
    mkdir -p "$dest"
    cp "$skill_dir/SKILL.md" "$dest/SKILL.md"
    echo "  Installed /$skill_name (always refreshed from source)."
done

# ── 11. Install agents to ~/.claude/agents/ ───────────────────────────────────
echo "[11/12] Installing agents to ~/.claude/agents/..."
mkdir -p "$HOME/.claude/agents"
for agent in "$LOOM_SRC/assets/agents/"*.md; do
    [ -f "$agent" ] || continue
    cp "$agent" "$HOME/.claude/agents/$(basename "$agent")"
    echo "  Installed $(basename "$agent")"
done

# ── 12. Shell aliases ─────────────────────────────────────────────────────────
echo "[12/12] Installing shell aliases..."

REAL_CLAUDE_PATH="$(command -v claude 2>/dev/null || echo "")"
if [ -z "$REAL_CLAUDE_PATH" ]; then
    echo "  WARNING: claude binary not found in PATH. LOOM_REAL_CLAUDE will be empty."
    echo "  Install claude first, then re-run install.sh."
fi

ALIAS_MARKER="# loom-code"
ALIAS_BLOCK="$ALIAS_MARKER — managed by install.sh, do not edit manually
export LOOM_SRC=\"$LOOM_SRC\"
export LOOM_HOME=\"$LOOM_HOME\"
export LOOM_REAL_CLAUDE=\"$REAL_CLAUDE_PATH\"
alias claude='\$LOOM_SRC/scripts/claude-wrapper.sh'
alias loom-install='\$LOOM_SRC/install.sh'
alias loom-bootstrap='\$LOOM_SRC/bootstrap-project.sh'
alias loom-reflect='\$LOOM_HOME/.venv/bin/python \$LOOM_SRC/scripts/reflect.py'
alias loom-stats='\$LOOM_HOME/.venv/bin/python \$LOOM_SRC/scripts/stats.py'
alias loom-approve='\$LOOM_HOME/.venv/bin/python \$LOOM_SRC/scripts/approve.py'
alias loom-config='\$LOOM_HOME/.venv/bin/python \$LOOM_SRC/scripts/config.py'
alias loom-test='cd \$LOOM_SRC && \$LOOM_HOME/.venv/bin/pytest tests/ -v && cd -'
$ALIAS_MARKER — end"

for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [ -f "$RC" ] || continue

    if grep -q "$ALIAS_MARKER" "$RC" 2>/dev/null; then
        # Replace existing loom-code block
        python3 - "$RC" "$ALIAS_BLOCK" <<'PYEOF'
import sys, re
rc_path, block = sys.argv[1], sys.argv[2]
with open(rc_path) as f:
    content = f.read()
pattern = r'# loom-code.*?# loom-code — end\n?'
new_content = re.sub(pattern, block + '\n', content, flags=re.DOTALL)
with open(rc_path, 'w') as f:
    f.write(new_content)
PYEOF
        echo "  Updated aliases in $RC"
    else
        printf '\n%s\n' "$ALIAS_BLOCK" >> "$RC"
        echo "  Appended aliases to $RC"
    fi
done

# ── Session guard: SessionStart hook ──────────────────────────────────────────
GUARD_DEST="$LOOM_HOME/scripts/session-guard.sh"
mkdir -p "$LOOM_HOME/scripts"
cp "$LOOM_SRC/scripts/session-guard.sh" "$GUARD_DEST"
chmod +x "$GUARD_DEST"

SETTINGS_JSON="$HOME/.claude/settings.json"
python3 - "$SETTINGS_JSON" "$GUARD_DEST" <<'PYEOF'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
guard_script = sys.argv[2]
guard_cmd = f'bash "{guard_script}"'

data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
data.setdefault("hooks", {})

# Remove legacy UserPromptSubmit entry if present (migrating to SessionStart)
ups = data["hooks"].get("UserPromptSubmit", [])
cleaned = [e for e in ups if not any(h.get("command") == guard_cmd for h in e.get("hooks", []))]
if cleaned != ups:
    data["hooks"]["UserPromptSubmit"] = cleaned
    print("  Removed legacy UserPromptSubmit session guard (migrating to SessionStart).")

existing_entries = data["hooks"].get("SessionStart", [])

# Idempotent: skip if our command is already registered
for entry in existing_entries:
    for hook in entry.get("hooks", []):
        if hook.get("command") == guard_cmd:
            print("  Session guard hook already registered, skipping.")
            sys.exit(0)

existing_entries.append({
    "matcher": "",
    "hooks": [{"type": "command", "command": guard_cmd}],
})
data["hooks"]["SessionStart"] = existing_entries

settings_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  Registered SessionStart hook in {settings_path}")
PYEOF

# ── Secrets scanner: PreToolUse hook ──────────────────────────────────────────
SECRETS_DEST="$LOOM_HOME/scripts/secrets-check.sh"
cp "$LOOM_SRC/scripts/secrets-check.sh" "$SECRETS_DEST"
chmod +x "$SECRETS_DEST"

python3 - "$SETTINGS_JSON" "$SECRETS_DEST" <<'PYEOF'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
script = sys.argv[2]
cmd = f'bash "{script}"'

data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
data.setdefault("hooks", {})
existing = data["hooks"].get("PreToolUse", [])

for entry in existing:
    for hook in entry.get("hooks", []):
        if hook.get("command") == cmd:
            print("  Secrets scanner hook already registered, skipping.")
            sys.exit(0)

existing.append({
    "matcher": "Write|Edit",
    "hooks": [{"type": "command", "command": cmd}],
})
data["hooks"]["PreToolUse"] = existing

settings_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  Registered PreToolUse secrets scanner in {settings_path}")
PYEOF

# ── Session timeout: Stop hook ─────────────────────────────────────────────────
TIMEOUT_DEST="$LOOM_HOME/scripts/session-timeout-check.sh"
cp "$LOOM_SRC/scripts/session-timeout-check.sh" "$TIMEOUT_DEST"
chmod +x "$TIMEOUT_DEST"

python3 - "$SETTINGS_JSON" "$TIMEOUT_DEST" <<'PYEOF'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
script = sys.argv[2]
cmd = f'bash "{script}"'

data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
data.setdefault("hooks", {})
existing = data["hooks"].get("Stop", [])

for entry in existing:
    for hook in entry.get("hooks", []):
        if hook.get("command") == cmd:
            print("  Session timeout hook already registered, skipping.")
            sys.exit(0)

existing.append({
    "matcher": "",
    "hooks": [{"type": "command", "command": cmd}],
})
data["hooks"]["Stop"] = existing

settings_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  Registered Stop session timeout hook in {settings_path}")
PYEOF

# ── PreCompact context snapshot hook ──────────────────────────────────────────
PRECOMPACT_SH="$LOOM_HOME/scripts/pre-compact-snapshot.sh"
PRECOMPACT_PY="$LOOM_HOME/scripts/pre-compact-snapshot.py"
cp "$LOOM_SRC/scripts/pre-compact-snapshot.sh" "$PRECOMPACT_SH"
cp "$LOOM_SRC/scripts/pre-compact-snapshot.py" "$PRECOMPACT_PY"
chmod +x "$PRECOMPACT_SH"

python3 - "$SETTINGS_JSON" "$PRECOMPACT_SH" <<'PYEOF'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
script = sys.argv[2]
cmd = f'bash "{script}"'

data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
data.setdefault("hooks", {})
existing = data["hooks"].get("PreCompact", [])

for entry in existing:
    for hook in entry.get("hooks", []):
        if hook.get("command") == cmd:
            print("  PreCompact snapshot hook already registered, skipping.")
            sys.exit(0)

existing.append({
    "matcher": "",
    "hooks": [{"type": "command", "command": cmd}],
})
data["hooks"]["PreCompact"] = existing

settings_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  Registered PreCompact context snapshot hook in {settings_path}")
PYEOF

# ── SubagentStop agent-feedback capture hook ──────────────────────────────────
SUBAGENT_SH="$LOOM_HOME/scripts/subagent-stop-capture.sh"
SUBAGENT_PY="$LOOM_HOME/scripts/subagent-stop-capture.py"
cp "$LOOM_SRC/scripts/subagent-stop-capture.sh" "$SUBAGENT_SH"
cp "$LOOM_SRC/scripts/subagent-stop-capture.py" "$SUBAGENT_PY"
chmod +x "$SUBAGENT_SH"

python3 - "$SETTINGS_JSON" "$SUBAGENT_SH" <<'PYEOF'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
script = sys.argv[2]
cmd = f'bash "{script}"'

data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
data.setdefault("hooks", {})
existing = data["hooks"].get("SubagentStop", [])

for entry in existing:
    for hook in entry.get("hooks", []):
        if hook.get("command") == cmd:
            print("  SubagentStop capture hook already registered, skipping.")
            sys.exit(0)

existing.append({
    "matcher": "",
    "hooks": [{"type": "command", "command": cmd}],
})
data["hooks"]["SubagentStop"] = existing

settings_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  Registered SubagentStop agent-feedback hook in {settings_path}")
PYEOF

# ── Auto-update loom-code section in ~/.claude/CLAUDE.md ──────────────────────
GLOBAL_CLAUDE_MD="$HOME/.claude/CLAUDE.md"
SNIPPET="$LOOM_SRC/assets/claude-md-snippet.md"

if [ -f "$GLOBAL_CLAUDE_MD" ]; then
    if grep -q "## Loom-Code Memory System" "$GLOBAL_CLAUDE_MD" 2>/dev/null; then
        # Replace existing loom-code section
        python3 - "$GLOBAL_CLAUDE_MD" "$SNIPPET" <<'PYEOF'
import sys
from pathlib import Path
claude_md = Path(sys.argv[1])
snippet = Path(sys.argv[2]).read_text()
content = claude_md.read_text()
idx = content.find("## Loom-Code Memory System")
base = content[:idx].rstrip('\n') + '\n\n'
claude_md.write_text(base + snippet)
PYEOF
        echo "  Updated loom-code section in $GLOBAL_CLAUDE_MD"
    else
        # Append for the first time
        printf '\n' >> "$GLOBAL_CLAUDE_MD"
        cat "$SNIPPET" >> "$GLOBAL_CLAUDE_MD"
        echo "  Appended loom-code section to $GLOBAL_CLAUDE_MD"
    fi
else
    echo "  $GLOBAL_CLAUDE_MD not found — create it and re-run, or add snippet manually."
    echo ""
    cat "$SNIPPET"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " loom-code installed successfully!"
echo "============================================================"
echo ""
echo "Source your shell rc (or open a new terminal) and restart Claude Code."
echo ""
echo "Aliases available after sourcing:"
echo "  loom-install    — re-run this installer (--update to skip wizard)"
echo "  loom-bootstrap  — wire quality hooks into the current project"
echo "  loom-config     — view/edit config (name, model, provider)"
echo "  loom-reflect    — run reflection pipeline manually"
echo "  loom-stats      — show memory stats"
echo "  loom-approve    — review and approve/reject directive proposals"
echo "  loom-test       — run loom-code test suite (dev only)"

# ── Optional: Status line ─────────────────────────────────────────────────────
SL_SRC="$LOOM_SRC/assets/statusline.sh"
SL_DEST="$HOME/.claude/statusline.sh"

if [ "$UPDATE_MODE" = true ] && [ -f "$SL_DEST" ]; then
    # Refresh existing script on --update
    cp "$SL_SRC" "$SL_DEST"
    chmod +x "$SL_DEST"
    echo "  Refreshed statusline.sh"
elif [ "$UPDATE_MODE" = true ] && [ ! -f "$SL_DEST" ]; then
    # New feature — offer to install on --update if not yet present
    echo ""
    echo "  New: loom-code status line (model, context window usage)"
    read -r -p "  Install it? (y/N): " INSTALL_SL
    INSTALL_SL="${INSTALL_SL:-N}"
    if [[ "$INSTALL_SL" =~ ^[Yy]$ ]]; then
        mkdir -p "$(dirname "$SL_DEST")"
        cp "$SL_SRC" "$SL_DEST"
        chmod +x "$SL_DEST"

        python3 - "$SETTINGS_JSON" "$SL_DEST" <<'PYEOF'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
script = sys.argv[2]

data = json.loads(settings_path.read_text()) if settings_path.exists() else {}

if "statusLine" in data:
    print("  Status line already configured, skipping.")
    sys.exit(0)

data["statusLine"] = {"type": "command", "command": script}

settings_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  Configured status line in {settings_path}")
PYEOF
        echo "  Status line installed."
    else
        echo "  Skipped."
    fi
elif ! $UPDATE_MODE; then
    echo ""
    echo "------------------------------------------------------------"
    echo " Optional: loom-code status line"
    echo ""
    echo "  Shows model and context window usage"
    echo "  in the Claude Code status bar."
    echo "------------------------------------------------------------"
    read -r -p "  Install status line? (y/N): " INSTALL_SL
    INSTALL_SL="${INSTALL_SL:-N}"
    if [[ "$INSTALL_SL" =~ ^[Yy]$ ]]; then
        mkdir -p "$(dirname "$SL_DEST")"
        cp "$SL_SRC" "$SL_DEST"
        chmod +x "$SL_DEST"

        python3 - "$SETTINGS_JSON" "$SL_DEST" <<'PYEOF'
import json, sys
from pathlib import Path

settings_path = Path(sys.argv[1])
script = sys.argv[2]

data = json.loads(settings_path.read_text()) if settings_path.exists() else {}

if "statusLine" in data:
    print("  Status line already configured, skipping.")
    sys.exit(0)

data["statusLine"] = {"type": "command", "command": script}

settings_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  Configured status line in {settings_path}")
PYEOF
        echo "  Status line installed."
    else
        echo "  Skipped."
    fi
fi

# ── Optional: LSP plugins for inline type checking ────────────────────────────
if ! $UPDATE_MODE; then
    echo ""
    echo "------------------------------------------------------------"
    echo " Optional: LSP plugins for inline type checking"
    echo ""
    echo "  pyright-lsp    — Python type errors surfaced mid-edit"
    echo "  typescript-lsp — TypeScript type errors surfaced mid-edit"
    echo ""
    echo "  These complement the quality-check.sh PostToolUse hook by"
    echo "  catching type errors in the same turn as the edit."
    echo "------------------------------------------------------------"
    read -r -p "  Install LSP plugins now? (y/N): " INSTALL_LSP
    INSTALL_LSP="${INSTALL_LSP:-N}"
    if [[ "$INSTALL_LSP" =~ ^[Yy]$ ]]; then
        echo ""
        echo "  Installing pyright-lsp..."
        claude plugin install pyright-lsp@anthropics/claude-code --scope user 2>/dev/null \
            && echo "  ✓ pyright-lsp installed" \
            || echo "  ✗ Install failed. Run manually inside Claude Code: /plugin install pyright-lsp@anthropics/claude-code"
        echo "  Installing typescript-lsp..."
        claude plugin install typescript-lsp@anthropics/claude-code --scope user 2>/dev/null \
            && echo "  ✓ typescript-lsp installed" \
            || echo "  ✗ Install failed. Run manually inside Claude Code: /plugin install typescript-lsp@anthropics/claude-code"
    else
        echo "  Skipped. Install later: claude plugin install pyright-lsp@anthropics/claude-code --scope user"
    fi
fi
