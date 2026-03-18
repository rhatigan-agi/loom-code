#!/usr/bin/env python3
"""PreCompact hook — queues a snapshot of working context before compaction.

Writes to ~/.loom-code/pending-captures/ (no embedding model needed).
loom_session_start drains the queue at the next session open.

Called by pre-compact-snapshot.sh, which is registered as a PreCompact hook
in ~/.claude/settings.json by install.sh.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

LOOM_HOME = Path(os.environ.get("LOOM_HOME", Path.home() / ".loom-code"))

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

messages = data.get("messages", [])
if not messages:
    sys.exit(0)

# Extract the last 3 user messages as working context
recent_user = [
    m["content"]
    for m in messages[-20:]
    if isinstance(m.get("content"), str) and m.get("role") == "user"
]
if not recent_user:
    sys.exit(0)

cwd = data.get("cwd", "")
project = Path(cwd).name if cwd else None

context_snippet = " | ".join(recent_user[-3:])[:600]
content = f"Pre-compaction context snapshot: {context_snippet}"

pending_dir = LOOM_HOME / "pending-captures"
pending_dir.mkdir(parents=True, exist_ok=True)

ts = datetime.now().strftime("%Y%m%dT%H%M%S%f")
record = {
    "content": content,
    "memory_type": "pre_compact_snapshot",
    "project": project,
    "tags": ["pre_compact", "context_continuity"],
    "salience": 0.72,
    "captured_at": datetime.now().isoformat(),
}
(pending_dir / f"{ts}-precompact.json").write_text(json.dumps(record))
print("loom-code: working context queued before compaction")
sys.exit(0)
