"""loom-code flat file synchronization.

Writes session notes and journals to markdown files.
Reads manually-edited directive files and re-embeds on change.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

import loom_mcp.config as cfg

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:50].strip("-")


def write_session_file(
    project: str,
    summary: str,
    learnings: list[str],
    surprises: list[str],
    tags: list[str],
    started_at: datetime,
) -> Path:
    """Write a session notes file.

    Returns:
        Path to the written file.
    """
    project_dir = cfg.SESSIONS_DIR / project
    project_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(summary[:50]) if summary else "session"
    timestamp = started_at.strftime("%Y-%m-%d_%H-%M")
    filename = f"{timestamp}_{slug}.md"
    filepath = project_dir / filename

    lines = [
        f"# Session: {summary}",
        f"**Project:** {project}",
        f"**Started:** {started_at.isoformat()}",
        f"**Ended:** {datetime.now().isoformat()}",
        "",
    ]

    if tags:
        lines.append(f"**Tags:** {', '.join(tags)}")
        lines.append("")

    if summary:
        lines.extend(["## Summary", summary, ""])

    if learnings:
        lines.append("## Learnings")
        for learning in learnings:
            lines.append(f"- {learning}")
        lines.append("")

    if surprises:
        lines.append("## Surprises")
        for surprise in surprises:
            lines.append(f"- {surprise}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Session file written", extra={"path": str(filepath)})
    return filepath


def write_journal_file(project: str, content: str, created_at: datetime) -> Path:
    """Write a journal entry file.

    Returns:
        Path to the written file.
    """
    cfg.JOURNALS_DIR.mkdir(parents=True, exist_ok=True)

    date_str = created_at.strftime("%Y-%m-%d")
    filename = f"{date_str}_{project}.md"
    filepath = cfg.JOURNALS_DIR / filename

    filepath.write_text(content, encoding="utf-8")
    logger.info("Journal file written", extra={"path": str(filepath)})
    return filepath


def read_identity() -> str:
    """Read the identity.md file, returning empty string if missing."""
    if not cfg.IDENTITY_FILE.exists():
        return ""
    return cfg.IDENTITY_FILE.read_text(encoding="utf-8")


def read_permanent_directives() -> str:
    """Read the permanent directives file."""
    if not cfg.PERMANENT_DIRECTIVES_FILE.exists():
        return ""
    return cfg.PERMANENT_DIRECTIVES_FILE.read_text(encoding="utf-8")


def read_domain_directives(domain: str) -> str:
    """Read domain-specific directives."""
    filepath = cfg.DOMAIN_DIRECTIVES_DIR / f"{domain}.md"
    if not filepath.exists():
        return ""
    return filepath.read_text(encoding="utf-8")


def read_project_directives(project: str) -> str:
    """Read project-specific directives."""
    filepath = cfg.PROJECT_DIRECTIVES_DIR / f"{project}.md"
    if not filepath.exists():
        return ""
    return filepath.read_text(encoding="utf-8")


def get_all_directive_files() -> list[Path]:
    """List all directive files."""
    files: list[Path] = []
    if cfg.PERMANENT_DIRECTIVES_FILE.exists():
        files.append(cfg.PERMANENT_DIRECTIVES_FILE)

    if cfg.DOMAIN_DIRECTIVES_DIR.exists():
        files.extend(sorted(cfg.DOMAIN_DIRECTIVES_DIR.glob("*.md")))

    if cfg.PROJECT_DIRECTIVES_DIR.exists():
        files.extend(sorted(cfg.PROJECT_DIRECTIVES_DIR.glob("*.md")))

    return files


def _content_already_present(existing: str, addition: str, window: int = 60) -> bool:
    """Return True if the addition is already substantially present in existing.

    Takes the first `window` chars of each bullet in the addition as a fingerprint
    and checks whether that fingerprint appears anywhere in the normalized existing
    content. Uses 60 chars by default — long enough to be distinctive, short enough
    to survive minor rewording of the tail of a rule.

    Args:
        existing: Current file content.
        addition: Content about to be appended.
        window: Character window for fingerprinting each bullet.
    """
    existing_normalized = re.sub(r"\s+", " ", existing.lower())
    for line in addition.splitlines():
        body = line.strip().lstrip("- ").strip()
        if len(body) < 30:
            continue
        fingerprint = re.sub(r"\s+", " ", body[:window]).lower()
        if fingerprint in existing_normalized:
            return True
    return False


def dedup_directive_file(directive_file: str) -> int:
    """Remove duplicate bullet points from a directive file in-place.

    Two bullets are considered duplicates if their first 60 normalized chars
    match. The first occurrence is kept; subsequent duplicates are dropped.
    Returns the number of duplicates removed.

    Args:
        directive_file: Relative path within the directives directory.
    """
    filepath = cfg.DIRECTIVES_DIR / directive_file
    if not filepath.exists():
        return 0

    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()

    seen: set[str] = set()
    output: list[str] = []
    removed = 0

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("- ") or len(stripped) < 30:
            output.append(line)
            continue

        body = stripped.lstrip("- ").strip()
        fingerprint = re.sub(r"\s+", " ", body[:60]).lower()

        if fingerprint in seen:
            removed += 1
        else:
            seen.add(fingerprint)
            output.append(line)

    filepath.write_text("\n".join(output) + "\n", encoding="utf-8")
    logger.info(
        "Directive dedup complete",
        extra={"file": directive_file, "removed": removed},
    )
    return removed


def _resolve_agent_skill_paths(directive_file: str) -> list[Path]:
    """Resolve target paths for agent/skill file updates.

    Agent and skill files are written to:
      1. ~/.claude/agents/<name>.md  or  ~/.claude/skills/<path>
      2. LOOM_SRC_PATH/assets/<directive_file>  (so reinstall doesn't regress)

    Args:
        directive_file: Relative path starting with 'agents/' or 'skills/'.

    Returns:
        List of absolute Paths to write to.
    """
    paths: list[Path] = []

    if directive_file.startswith("agents/"):
        rel = directive_file[len("agents/"):]
        paths.append(cfg.CLAUDE_AGENTS_DIR / rel)
    elif directive_file.startswith("skills/"):
        rel = directive_file[len("skills/"):]
        paths.append(cfg.CLAUDE_SKILLS_DIR / rel)

    if cfg.LOOM_SRC_PATH is not None:
        src_path = cfg.LOOM_SRC_PATH / "assets" / directive_file
        paths.append(src_path)

    return paths


def apply_directive_diff(directive_file: str, proposed_diff: str) -> None:
    """Apply an approved diff to a directive file.

    For simplicity, the proposed_diff is treated as the new content to append
    or the full replacement content, depending on context markers.
    Append operations are skipped if the content is already substantially
    present in the file (dedup guard).

    Agent and skill files (agents/*.md, skills/**/*.md) are written to both
    ~/.claude/ (active) and LOOM_SRC_PATH/assets/ (source), so reinstalls
    don't regress approved changes.

    Args:
        directive_file: Relative path within the directives directory,
            or 'agents/<name>.md' / 'skills/<path>' for agent/skill updates.
        proposed_diff: The content change to apply.
    """
    is_agent_skill = directive_file.startswith("agents/") or directive_file.startswith(
        "skills/"
    )

    if is_agent_skill:
        filepaths = _resolve_agent_skill_paths(directive_file)
        if not filepaths:
            logger.warning(
                "No target paths resolved for agent/skill file",
                extra={"file": directive_file},
            )
            return
    else:
        filepaths = [cfg.DIRECTIVES_DIR / directive_file]

    for fp in filepaths:
        fp.parent.mkdir(parents=True, exist_ok=True)

    # Use the first path as the source-of-truth for dedup checks
    primary = filepaths[0]

    if proposed_diff.startswith("REPLACE:") and re.search(r"\nWITH:\s*\n", proposed_diff):
        # Targeted replacement: REPLACE:\n<old>\n\nWITH:\n\n<new>
        # Used by 'modify' change_type to update a specific bullet without wiping the file.
        body = proposed_diff[len("REPLACE:"):].strip()
        with_match = re.search(r"\nWITH:\s*\n", body)
        old_text = body[: with_match.start()].strip()
        new_text = body[with_match.end() :].strip()
        existing = primary.read_text(encoding="utf-8") if primary.exists() else ""
        if old_text not in existing:
            logger.warning(
                "Targeted REPLACE: target not found in directive file — skipping",
                extra={"file": directive_file, "target": old_text[:80]},
            )
            return
        updated = existing.replace(old_text, new_text, 1)
        if not updated.endswith("\n"):
            updated += "\n"
        for fp in filepaths:
            fp.write_text(updated, encoding="utf-8")
        logger.info("Directive targeted-replace applied", extra={"file": directive_file})
    elif proposed_diff.startswith("REPLACE:"):
        # Full replacement — no dedup needed (used for 'consolidate' type)
        new_content = proposed_diff[len("REPLACE:"):].strip() + "\n"
        for fp in filepaths:
            fp.write_text(new_content, encoding="utf-8")
        logger.info("Directive replaced", extra={"file": directive_file})
    elif proposed_diff.startswith("APPEND:"):
        addition = proposed_diff[len("APPEND:"):].strip()
        existing = primary.read_text(encoding="utf-8") if primary.exists() else ""
        if _content_already_present(existing, addition):
            logger.info(
                "Directive append skipped — content already present",
                extra={"file": directive_file},
            )
            return
        new_content = existing.rstrip() + "\n\n" + addition + "\n"
        for fp in filepaths:
            fp_existing = fp.read_text(encoding="utf-8") if fp.exists() else ""
            fp.write_text(fp_existing.rstrip() + "\n\n" + addition + "\n", encoding="utf-8")
        logger.info("Directive appended", extra={"file": directive_file})
    elif re.match(r"^[A-Z]{2,}:", proposed_diff.strip()):
        # Unknown command prefix (e.g. CONSOLIDATE:, MODIFY:) — skip rather than
        # appending the literal command text into the directive file.
        prefix = proposed_diff.strip().split(":")[0]
        logger.warning(
            "Directive diff has unrecognised prefix — skipped. Use APPEND: or REPLACE:.",
            extra={"file": directive_file, "prefix": prefix},
        )
    else:
        # Default: append with dedup guard (used for agent/skill plain-text replacements)
        addition = proposed_diff.strip()
        existing = primary.read_text(encoding="utf-8") if primary.exists() else ""
        if _content_already_present(existing, addition):
            logger.info(
                "Directive append skipped — content already present",
                extra={"file": directive_file},
            )
            return
        for fp in filepaths:
            fp_existing = fp.read_text(encoding="utf-8") if fp.exists() else ""
            fp.write_text(
                fp_existing.rstrip() + "\n\n" + addition + "\n",
                encoding="utf-8",
            )
        logger.info("Directive updated", extra={"file": directive_file})


def find_similar_directive(
    proposed_content: str,
    directive_file: str,
    threshold: float = 0.82,
) -> str | None:
    """Semantic similarity check against existing rules in a directive file.

    Uses batch embedding to compare proposed content against every bullet rule
    in the target file. Returns the most similar existing rule if similarity
    exceeds threshold, None otherwise.

    Skips agent/skill files — their structure doesn't match bullet-rule comparison.

    Args:
        proposed_content: The proposed directive text.
        directive_file: Relative path within the directives directory.
        threshold: Cosine similarity threshold (default 0.82).

    Returns:
        The similar existing rule text, or None if no match found.
    """
    if directive_file.startswith("agents/") or directive_file.startswith("skills/"):
        return None

    filepath = cfg.DIRECTIVES_DIR / directive_file
    if not filepath.exists():
        return None

    content = filepath.read_text(encoding="utf-8")
    rules = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("- ") and len(line.strip()) > 40
    ]
    if not rules:
        return None

    from loom_mcp.embeddings import embed_batch, search

    all_embeddings = embed_batch(rules + [proposed_content])
    proposed_emb = all_embeddings[-1]
    rule_candidates = [(str(i), emb) for i, emb in enumerate(all_embeddings[:-1])]

    ranked = search(proposed_emb, rule_candidates)
    if ranked and ranked[0][1] >= threshold:
        return rules[int(ranked[0][0])]
    return None


def get_directive_stats() -> dict:
    """Return size and health stats for all directive files.

    Returns:
        Dict with per-file stats and an overall token estimate.
    """
    files_stats = []
    total_tokens = 0
    warnings = []

    for filepath in get_all_directive_files():
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        bullets = sum(
            1 for line in content.splitlines() if line.strip().startswith("- ")
        )
        est_tokens = len(content) // 4
        rel_path = str(filepath.relative_to(cfg.DIRECTIVES_DIR))
        files_stats.append(
            {
                "file": rel_path,
                "bullets": bullets,
                "lines": len(content.splitlines()),
                "est_tokens": est_tokens,
            }
        )
        total_tokens += est_tokens
        if est_tokens > 2000:
            warnings.append(f"{rel_path}: {est_tokens} est. tokens — consider consolidating")

    return {
        "directive_files": files_stats,
        "directive_total_est_tokens": total_tokens,
        "directive_warnings": warnings,
    }


def detect_changed_files(mtimes: dict[str, float]) -> list[Path]:
    """Detect manually-edited directive files by comparing mtimes.

    Args:
        mtimes: Dict of filepath -> last known mtime.

    Returns:
        List of files that have been modified since last check.
    """
    changed: list[Path] = []
    for filepath in get_all_directive_files():
        key = str(filepath)
        current_mtime = filepath.stat().st_mtime
        if key in mtimes:
            if current_mtime > mtimes[key]:
                changed.append(filepath)
        else:
            changed.append(filepath)
    return changed
