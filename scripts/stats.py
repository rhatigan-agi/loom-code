#!/usr/bin/env python3
"""CLI tool for loom-code memory statistics."""

import json
import logging
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Print memory system statistics."""
    from loom_mcp.init_db import init_database

    init_database()

    from loom_mcp.file_sync import get_directive_stats
    from loom_mcp.memory import get_memory_stats

    stats = get_memory_stats()
    directive_stats = get_directive_stats()

    # Memory stats
    print(json.dumps(stats, indent=2, default=str))

    # Directive file breakdown
    print("\n── Directive Files ──────────────────────────────────────")
    files = directive_stats.get("directive_files", [])
    if files:
        print(f"  {'File':<35}  {'Bullets':>7}  {'Est. Tokens':>11}")
        print(f"  {'─' * 35}  {'─' * 7}  {'─' * 11}")
        for f in files:
            warn = "  [!]" if f["est_tokens"] > 2000 else ""
            print(f"  {f['file']:<35}  {f['bullets']:>7}  {f['est_tokens']:>11}{warn}")
        total = directive_stats["directive_total_est_tokens"]
        print(f"  {'─' * 35}  {'─' * 7}  {'─' * 11}")
        print(f"  {'TOTAL':<35}  {'':>7}  {total:>11}")
    else:
        print("  (no directive files found)")

    warnings = directive_stats.get("directive_warnings", [])
    if warnings:
        print()
        for w in warnings:
            print(f"  WARNING: {w}")


if __name__ == "__main__":
    main()
