#!/usr/bin/env bash
# loom-code secrets scanner — wired as a PreToolUse hook in ~/.claude/settings.json.
# Fires before Write and Edit tool calls. Checks content for credential patterns.
# Exits non-zero to block the write if a secret is detected.
# Exits 0 to allow all other tools or clean writes through.

python3 - <<'PYEOF'
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")
if tool_name not in ("Write", "Edit"):
    sys.exit(0)

ti = data.get("tool_input", {})
file_path = ti.get("file_path", "")

# Exempt .env.example and test/fixture files — they legitimately contain placeholder patterns
exempt_patterns = [".env.example", ".env.sample", ".env.test", "fixture", "test_data"]
if any(p in file_path for p in exempt_patterns):
    sys.exit(0)

# Combine Write content and Edit new_string into one blob to scan
content = ti.get("content", "") + "\n" + ti.get("new_string", "")

PATTERNS = [
    (r"sk-ant-[a-zA-Z0-9_\-]{20,}", "Anthropic API key"),
    (r"sk-proj-[a-zA-Z0-9_\-]{40,}", "OpenAI project API key"),
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
    (r"ghs_[a-zA-Z0-9]{36}", "GitHub app token"),
    (r"github_pat_[a-zA-Z0-9_]{82}", "GitHub fine-grained PAT"),
    (r"AKIA[A-Z0-9]{16}", "AWS access key ID"),
    (r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY", "private key"),
]

for pattern, label in PATTERNS:
    if re.search(pattern, content):
        # Write to stderr: exit 2 sends stderr to Claude per hook spec
        print(f"BLOCKED: Potential {label} detected in {file_path or 'content'}.", file=sys.stderr)
        print("Store credentials in environment variables or a secrets manager, not in files.", file=sys.stderr)
        print("If this is a placeholder or test value, rename the file to *.env.example.", file=sys.stderr)
        sys.exit(2)

sys.exit(0)
PYEOF
