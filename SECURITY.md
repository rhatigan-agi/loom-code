# Security

## Data Model

loom-code stores all data locally on your machine. Nothing leaves your system except:

- **LLM API calls during `loom-reflect`** — sends session summaries and memory content to your configured reflection provider (Anthropic, Ollama, or OpenAI-compatible endpoint). This only happens when you explicitly run `loom-reflect` or `/reflect`.
- **Embedding model download** — downloads `all-MiniLM-L6-v2` from Hugging Face on first install. After that, embeddings run entirely locally.

No telemetry. No analytics. No phone-home.

## Where Secrets Are Stored

| Secret | Location | Permissions |
|--------|----------|-------------|
| Reflection API key | `~/.loom-code/.env` | `chmod 600` (owner-only read/write) |
| Claude Code API key | Managed by Claude Code, not by loom-code | N/A |

The `.env` file is created by the installer with `chmod 600` and is listed in `.gitignore`.

## Secrets Scanner

loom-code installs a `PreToolUse` hook (`secrets-check.sh`) that scans every `Write` and `Edit` operation for credential patterns before they reach disk:

- Anthropic API keys (`sk-ant-*`)
- OpenAI API keys (`sk-*`)
- AWS keys (`AKIA*`)
- Generic `password=` / `secret=` patterns
- Base64-encoded key patterns

If a pattern matches, the write is **blocked** and Claude is told why. Test and fixture files are exempted.

## Database

`~/.loom-code/db/loom.db` is a SQLite database containing memories, session summaries, journal entries, and directive proposals. It uses:

- Parameterized queries throughout (no string interpolation in SQL)
- WAL journal mode
- Foreign keys enabled

The database contains your coding patterns and session history — treat it as sensitive.

## Auditing

To see what data loom-code has stored:

```bash
loom-stats                              # summary counts
sqlite3 ~/.loom-code/db/loom.db ".tables"  # list tables
sqlite3 ~/.loom-code/db/loom.db "SELECT content FROM memories LIMIT 5"  # sample
```

## Reporting Vulnerabilities

If you find a security issue, please open a GitHub issue or email jeff@rhatigan.dev. I'll respond promptly.
