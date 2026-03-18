# Contributing to loom-code

Thanks for your interest. Here's what you need to know.

## Setup

```bash
git clone https://github.com/rhatigan-agi/loom-code.git
cd loom-code
python3.12 -m venv .venv
.venv/bin/pip install -e . -r requirements-dev.txt
```

## Quality Checks

All of these must pass before submitting a PR:

```bash
# Tests
.venv/bin/pytest tests/ -v

# Linting
.venv/bin/ruff check .

# Type checking
.venv/bin/mypy loom_mcp/
```

## Standards

- **Python 3.12+** required
- **No `print()`** in library code — use `logger.info("msg", extra={...})`
- **Type hints** on all function signatures
- **Docstrings** on public functions (Google style)
- **`pathlib`** over `os.path`
- **Structured logging** with `extra={}` dicts
- **mypy strict** mode — no `Any` types without justification
- **ruff** with rules E, F, I, UP

## Testing

- Tests run fast, fail fast
- One assertion concept per test
- Use `tmp_path` fixtures for isolation — never touch `~/.loom-code` in tests
- Mock external calls (`_call_claude`, embedding model) to avoid API dependencies
- All tests must pass without API keys

## PR Process

1. Fork the repo and create a feature branch
2. Make your changes
3. Run all quality checks (above)
4. Open a PR with a clear description of what changed and why
5. One approval required to merge

## Commit Format

```
type(scope): description
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Reporting Issues

Open an issue on GitHub. Include:
- What you expected
- What happened
- Steps to reproduce
- `loom-stats` output if relevant
- Python version and OS

## Architecture Overview

If you're making non-trivial changes, read the Architecture section in the README first. The key separation:
- `~/.claude/` — Claude's native config (hooks, agents, skills, CLAUDE.md)
- `~/.loom-code/` — loom-code's data (identity, directives, memories, db)
- `loom_mcp/` — the MCP server and all core logic
- `scripts/` — CLI tools and hook scripts
