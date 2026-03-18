#!/usr/bin/env bash
# loom-code status line for Claude Code
# Receives JSON on stdin from Claude Code, outputs colored status text.
INPUT=$(cat)
printf '%s' "$INPUT" | python3 -c '
import json, os, sys

# 256-color ANSI palette
P  = "\033[38;5;209m"   # coral        — brand, model
D  = "\033[38;5;243m"   # dim gray     — separators
BE = "\033[38;5;238m"   # dark gray    — bar empty
R  = "\033[0m"          # reset

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

model = data.get("model", {}).get("display_name", "").replace("claude-", "")
ctx = data.get("context_window", {}).get("used_percentage", 0)
project = os.path.basename(data.get("cwd", "") or os.getcwd())

# Bar fill color scales with context usage
if ctx >= 90:
    BF = "\033[38;5;203m"   # red-orange   — critical
elif ctx >= 75:
    BF = "\033[38;5;214m"   # amber        — warning
else:
    BF = P                   # coral        — normal

# Context bar
w = 10
n = min(round(ctx * w / 100), w)
bar = f"{BF}{chr(9608) * n}{BE}{chr(9617) * (w - n)}{R}"

# Assemble
parts = [f"{P}loom-code{R}"]
if project:
    parts.append(f"{P}/{project}{R}")
if model:
    parts.append(f"{P}{model}{R}")
parts.append(f"{bar} {BF}{ctx:.0f}%{R}")

sep = f" {D}\u2502{R} "
print(sep.join(parts), end="")
' 2>/dev/null
