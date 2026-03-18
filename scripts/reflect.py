#!/usr/bin/env python3
"""CLI wrapper for the loom-code reflection pipeline."""

import argparse
import json
import logging
import re
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _print_journal_summary(journal: dict) -> None:
    """Print a human-readable journal summary to stderr after reflection."""
    content: str = journal.get("content", "")
    file_path: str = journal.get("file_path", "")

    # Count open questions
    oq_match = re.search(
        r"\*\*Open Questions[^*]*\*\*:?\s*\n(.*?)(?:\n---|\n\*\*|\Z)",
        content,
        re.DOTALL,
    )
    oq_count = 0
    if oq_match:
        oq_count = sum(1 for line in oq_match.group(1).splitlines() if line.strip().startswith("- "))

    # First sentence of the narrative (after ---)
    excerpt = ""
    parts = content.split("\n---\n", 1)
    if len(parts) == 2:
        narrative = parts[1].strip()
        # Take up to the first period or 120 chars
        sentence_end = narrative.find(". ")
        if 0 < sentence_end < 120:
            excerpt = narrative[: sentence_end + 1]
        else:
            excerpt = narrative[:120].rstrip()

    print(f"\nJournal written \u2192 {file_path}", file=sys.stderr)
    print(f"  Open questions: {oq_count}", file=sys.stderr)
    if excerpt:
        print(f'  Excerpt: "{excerpt}"', file=sys.stderr)
    print("", file=sys.stderr)


def main() -> None:
    """Run the reflection pipeline from the command line."""
    parser = argparse.ArgumentParser(description="loom-code Reflection Pipeline")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--project", type=str, default=None, help="Project filter")
    parser.add_argument(
        "--mode",
        choices=["full", "journal", "directives"],
        default="full",
        help="Reflection mode (default: full)",
    )
    args = parser.parse_args()

    from loom_mcp.init_db import init_database

    init_database()

    from loom_mcp.reflection import run_reflection

    result = run_reflection(days=args.days, project=args.project, mode=args.mode)

    if journal := result.get("journal"):
        _print_journal_summary(journal)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
