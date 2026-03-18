"""
Close orphaned sessions — sessions that were started but never ended because
the Claude Code terminal was killed without a graceful exit.

Called by the claude-wrapper.sh on every claude process exit. Safe to run
concurrently: uses a 10-minute grace window so active sessions in other
terminals are not touched.

Usage:
    python -m loom_mcp.close_orphan
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone

import loom_mcp.config as cfg
from loom_mcp.config import ACTIVE_SESSIONS_DIR
from loom_mcp.init_db import get_connection

logger = logging.getLogger(__name__)


def close_orphan_sessions(grace_minutes: int = 10) -> int:
    """Close sessions with no end time that are older than grace_minutes.

    Args:
        grace_minutes: Sessions started within this window are assumed still
            active (protects concurrent sessions in other terminals).

    Returns:
        Number of sessions closed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=grace_minutes)
    cutoff_str = cutoff.isoformat()

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, project, started_at
            FROM sessions
            WHERE ended_at IS NULL
              AND started_at < ?
            """,
            (cutoff_str,),
        ).fetchall()

        if not rows:
            return 0

        now_str = datetime.now(timezone.utc).isoformat()
        closed = 0
        for row in rows:
            conn.execute(
                """
                UPDATE sessions
                SET ended_at = ?,
                    summary = ?,
                    learnings = ?
                WHERE id = ?
                """,
                (
                    now_str,
                    "Session closed without graceful exit (terminal killed).",
                    json.dumps(["No learnings recorded — session was force-closed."]),
                    row["id"],
                ),
            )
            logger.info(
                "Closed orphan session",
                extra={"session_id": row["id"], "project": row["project"]},
            )
            closed += 1

        conn.commit()
        return closed
    finally:
        conn.close()


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Clear all per-project sentinels on exit — any that remain are orphaned.
    if ACTIVE_SESSIONS_DIR.exists():
        for sentinel in ACTIVE_SESSIONS_DIR.iterdir():
            sentinel.unlink(missing_ok=True)

    if not cfg.DB_PATH.exists():
        # No DB yet — nothing to close.
        sys.exit(0)

    closed = close_orphan_sessions()
    if closed:
        logger.warning("Closed orphaned sessions", extra={"count": closed})


if __name__ == "__main__":
    main()
