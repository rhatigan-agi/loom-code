"""loom-code configuration: paths and constants."""

import os
from pathlib import Path


def _load_env_file(env_file: Path) -> None:
    """Load key=value pairs from env file into os.environ if not already set."""
    if not env_file.exists():
        return
    with env_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


# Root directory — override with LOOM_HOME env var
LOOM_HOME: Path = Path(os.environ.get("LOOM_HOME", Path.home() / ".loom-code"))

# .env file path — loaded at import time before reading other env vars
ENV_FILE: Path = LOOM_HOME / ".env"
_load_env_file(ENV_FILE)

# Directory paths
DIRECTIVES_DIR: Path = LOOM_HOME / "directives"
DOMAIN_DIRECTIVES_DIR: Path = DIRECTIVES_DIR / "by-domain"
PROJECT_DIRECTIVES_DIR: Path = DIRECTIVES_DIR / "by-project"
SESSIONS_DIR: Path = LOOM_HOME / "sessions"
JOURNALS_DIR: Path = LOOM_HOME / "journals"
DB_DIR: Path = LOOM_HOME / "db"
MODEL_CACHE_DIR: Path = LOOM_HOME / ".model-cache"

# File paths
IDENTITY_FILE: Path = LOOM_HOME / "identity.md"
PERMANENT_DIRECTIVES_FILE: Path = DIRECTIVES_DIR / "permanent.md"
DB_PATH: Path = DB_DIR / "loom.db"
ACTIVE_SESSIONS_DIR: Path = LOOM_HOME / ".active_sessions"
PENDING_CAPTURES_DIR: Path = LOOM_HOME / "pending-captures"

# User identity — set during install wizard
USER_NAME: str = os.environ.get("LOOM_USER_NAME", "")
ASSISTANT_NAME: str = "Loomy"

# Source path — set during install so the approve pipeline can update source files
LOOM_SRC_PATH: Path | None = (
    Path(os.environ["LOOM_SRC_PATH"])
    if os.environ.get("LOOM_SRC_PATH")
    else None
)

# Installed agent/skill directories (Claude Code reads from these)
CLAUDE_AGENTS_DIR: Path = Path.home() / ".claude" / "agents"
CLAUDE_SKILLS_DIR: Path = Path.home() / ".claude" / "skills"

# Embedding constants
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
EMBEDDING_DIM: int = 384

# Memory constants
DEFAULT_SALIENCE: float = 0.5
DECAY_RATE: float = 0.95
NEAR_DUPLICATE_THRESHOLD: float = 0.95
HIGH_SALIENCE_THRESHOLD: float = 0.8
ARCHIVE_SALIENCE_THRESHOLD: float = 0.25
RECONSOLIDATION_IMMUNITY_DAYS: int = 30

# Reflection defaults
DEFAULT_REFLECT_DAYS: int = 7
REFLECTION_MODEL: str = os.environ.get(
    "LOOM_REFLECTION_MODEL", "claude-haiku-4-5-20251001"
)
# Base URL for reflection API.
# Defaults to Anthropic API. Override with LOOM_REFLECTION_BASE_URL for Ollama or any
# OpenAI-compatible endpoint (e.g. "http://localhost:11434" for local Ollama).
REFLECTION_BASE_URL: str = os.environ.get(
    "LOOM_REFLECTION_BASE_URL", "https://api.anthropic.com"
)
# API key for reflection. Real Anthropic key if hitting api.anthropic.com;
# any non-empty value works for Ollama. Falls back to ANTHROPIC_API_KEY, then "ollama".
REFLECTION_API_KEY: str = (
    os.environ.get("LOOM_REFLECTION_API_KEY")
    or os.environ.get("ANTHROPIC_API_KEY")
    or "ollama"
)

# Per-step model overrides — each defaults to REFLECTION_MODEL if not set.
# Route the high-judgment Critic to a stronger model while keeping cheaper steps
# on a lighter model. Any model string accepted (Anthropic, Ollama, OpenAI-compat).
# Examples:
#   LOOM_CRITIC_MODEL=claude-sonnet-4-5-20251101  # stronger Critic for Anthropic users
#   LOOM_CRITIC_MODEL=qwen3:8b                    # stronger local Ollama model
WEAVER_MODEL: str = os.environ.get("LOOM_WEAVER_MODEL", REFLECTION_MODEL)
CRITIC_MODEL: str = os.environ.get("LOOM_CRITIC_MODEL", REFLECTION_MODEL)
RECONSOLIDATION_MODEL: str = os.environ.get("LOOM_RECONSOLIDATION_MODEL", REFLECTION_MODEL)
