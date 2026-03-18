#!/usr/bin/env python3
"""SubagentStop hook — captures agent-feedback comments from subagent output.

Scans for <!-- agent-feedback: agent-name: content --> patterns and writes
matches to ~/.loom-code/pending-captures/ (no embedding model needed).
loom_session_start drains the queue at the next session open.

Called by subagent-stop-capture.sh, registered as a SubagentStop hook
in ~/.claude/settings.json by install.sh.
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

LOOM_HOME = Path(os.environ.get("LOOM_HOME", Path.home() / ".loom-code"))
FEEDBACK_PATTERN = re.compile(
    r"<!--\s*agent-feedback:\s*([\w-]+):\s*(.+?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

# SubagentStop payload: output may be in "output" or "content" or "result"
output = (
    data.get("output")
    or data.get("content")
    or data.get("result")
    or ""
)
if not isinstance(output, str) or not output:
    sys.exit(0)

matches = FEEDBACK_PATTERN.findall(output)
if not matches:
    sys.exit(0)

cwd = data.get("cwd", "")
project = Path(cwd).name if cwd else None

pending_dir = LOOM_HOME / "pending-captures"
pending_dir.mkdir(parents=True, exist_ok=True)

for agent_name, feedback_content in matches:
    ts = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    record = {
        "content": feedback_content.strip(),
        "memory_type": "agent_feedback",
        "project": project,
        "tags": [f"agent:{agent_name}"],
        "salience": 0.6,
        "captured_at": datetime.now().isoformat(),
    }
    (pending_dir / f"{ts}-agentfeedback.json").write_text(json.dumps(record))
    print(f"loom-code: agent-feedback from {agent_name} queued")

sys.exit(0)
