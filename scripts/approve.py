#!/usr/bin/env python3
"""CLI tool for reviewing and approving loom-code directive and agent change proposals."""

import argparse
import logging
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def _print_change(change: object) -> None:
    print(f"\n{'─' * 60}")
    print(f"  ID:       {change.id}")
    print(f"  File:     {change.directive_file}")
    print(f"  Type:     {change.change_type}")
    print(f"  Status:   {change.status}")
    print(f"\n  Reasoning:\n    {change.reasoning}")
    print(f"\n  Proposed diff:\n{change.proposed_diff}")


def main() -> None:
    """Review and approve/reject directive change proposals."""
    parser = argparse.ArgumentParser(
        description="loom-code: Approve or reject directive and agent change proposals",
    )
    parser.add_argument("change_id", nargs="?", help="Change ID to act on (omit to list pending)")
    parser.add_argument("decision", nargs="?", choices=["approve", "reject"], help="Decision")
    parser.add_argument("--all", action="store_true", help="Approve all pending changes")
    parser.add_argument("--reject-all", action="store_true", help="Reject all pending changes")
    args = parser.parse_args()

    from loom_mcp.file_sync import apply_directive_diff, dedup_directive_file
    from loom_mcp.init_db import init_database
    from loom_mcp.memory import (
        get_directive_change,
        get_pending_directive_changes,
        resolve_directive_change,
    )

    init_database()
    pending = get_pending_directive_changes()

    # List mode
    if not args.change_id and not args.all and not args.reject_all:
        if not pending:
            print("No pending directive changes.")
            return
        print(f"{len(pending)} pending directive change(s):")
        for change in pending:
            _print_change(change)
        print(f"\n{'─' * 60}")
        print("Usage: loom-approve <id> approve|reject")
        print("       loom-approve --all")
        print("       loom-approve --reject-all")
        return

    # Bulk mode
    _past = {"approve": "APPROVED", "reject": "REJECTED"}
    if args.all or args.reject_all:
        decision = "approve" if args.all else "reject"
        if not pending:
            print("No pending changes.")
            return
        print(f"\n{len(pending)} pending change(s):")
        for change in pending:
            print(f"  {change.id[:8]}  {change.directive_file}  ({change.change_type})")
        try:
            prompt = f"\n{decision.upper()} all {len(pending)} change(s)? (y/N): "
            confirm = input(prompt).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return
        if confirm != "y":
            print("Aborted.")
            return
        affected_files: set[str] = set()
        for change in pending:
            if decision == "approve":
                apply_directive_diff(change.directive_file, change.proposed_diff)
                affected_files.add(change.directive_file)
            resolve_directive_change(change.id, decision + "d")
            print(f"  {_past[decision]}  {change.id}  ({change.directive_file})")
        print(f"\n{len(pending)} change(s) {_past[decision].lower()}.")
        if decision == "approve" and affected_files:
            for directive_file in sorted(affected_files):
                removed = dedup_directive_file(directive_file)
                if removed:
                    print(f"  dedup: {directive_file} — {removed} duplicate(s) removed.")
        return

    # Single change mode
    if not args.decision:
        parser.error("Provide a decision: approve or reject")

    change = get_directive_change(args.change_id)
    if not change:
        print(f"Error: change '{args.change_id}' not found.")
        sys.exit(1)
    if change.status != "pending":
        print(f"Error: already resolved as '{change.status}'.")
        sys.exit(1)

    _print_change(change)
    print()

    if args.decision == "approve":
        apply_directive_diff(change.directive_file, change.proposed_diff)

    resolve_directive_change(args.change_id, args.decision + "d")
    if args.decision == "approve":
        print(f"APPROVED — {change.directive_file} updated.")
    else:
        print("REJECTED — no file changes.")


if __name__ == "__main__":
    main()
