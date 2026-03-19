#!/usr/bin/env python3
"""loom-code config viewer/editor — view or change ~/.loom-code/.env settings."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

FIELDS = [
    ("LOOM_USER_NAME", "Your name", False),
    ("LOOM_REFLECTION_MODEL", "Reflection model", False),
    ("LOOM_REFLECTION_BASE_URL", "Reflection provider base URL", False),
    ("LOOM_REFLECTION_API_KEY", "Reflection API key", True),
]


def _read_env(env_file: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not env_file.exists():
        return result
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def _write_env(env_file: Path, data: dict[str, str]) -> None:
    lines = []
    for key, value in data.items():
        lines.append(f"{key}={value}")
    env_file.write_text("\n".join(lines) + "\n")
    env_file.chmod(0o600)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def show(env_file: Path) -> None:
    """Print current config."""
    data = _read_env(env_file)
    print(f"\nloom-code config  ({env_file})\n")
    print(f"{'Key':<30}  {'Value'}")
    print("─" * 60)
    for key, label, secret in FIELDS:
        raw = data.get(key, "")
        display = _mask(raw) if secret and raw else (raw or "(not set)")
        print(f"  {key:<28}  {display}   # {label}")
    extra = {k: v for k, v in data.items() if k not in {f[0] for f in FIELDS}}
    for key, value in extra.items():
        print(f"  {key:<28}  {value}")
    print()
    print("  Tip: run 'loom-config --edit' to update settings")


def edit(env_file: Path, key: str, value: str) -> None:
    """Set a single key."""
    data = _read_env(env_file)
    data[key] = value
    _write_env(env_file, data)
    label = next((f[1] for f in FIELDS if f[0] == key), key)
    is_secret = next((f[2] for f in FIELDS if f[0] == key), False)
    display = _mask(value) if is_secret else value
    print(f"  {label} set to: {display}")


def _detect_provider(data: dict[str, str]) -> int:
    """Detect current provider from env data: 1=Anthropic, 2=Ollama, 3=Custom."""
    base_url = data.get("LOOM_REFLECTION_BASE_URL", "")
    api_key = data.get("LOOM_REFLECTION_API_KEY", "")
    if "anthropic" in base_url.lower():
        return 1
    if api_key == "ollama" or "11434" in base_url:
        return 2
    if base_url:
        return 3
    return 1  # default


def _prompt(label: str, current: str = "", secret: bool = False) -> str:
    """Prompt user for a value; returns new value or current if Enter pressed."""
    display = _mask(current) if secret and current else current
    suffix = f" [{display}]" if current else ""
    try:
        value = input(f"  {label}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        raise
    return value if value else current


def interactive(env_file: Path) -> None:
    """Interactive provider-aware config editor."""
    data = _read_env(env_file)
    print(f"\nloom-code config editor  ({env_file})")
    print("Press Enter to keep the current value.\n")

    # ── Non-provider fields ────────────────────────────────────────────────────
    try:
        result = _prompt("Your name", data.get("LOOM_USER_NAME", ""), False)
        if result:
            data["LOOM_USER_NAME"] = result
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return

    # ── Provider selection ─────────────────────────────────────────────────────
    current_provider = _detect_provider(data)
    print()
    print("  Which LLM provider for reflection?")
    labels = {
        1: "Anthropic API  (claude-haiku-4-5-20251001 — recommended)",
        2: "Ollama          (local, needs Ollama running)",
        3: "OpenAI-compatible endpoint  (vLLM, LiteLLM, etc.)",
    }
    for num, desc in labels.items():
        marker = " *" if num == current_provider else "  "
        print(f"{marker} {num}) {desc}")
    print()
    try:
        raw = input(f"  Choice [{current_provider}]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return
    choice = int(raw) if raw.isdigit() and int(raw) in labels else current_provider

    # ── Provider-specific fields ───────────────────────────────────────────────
    try:
        if choice == 1:
            current_key = data.get("LOOM_REFLECTION_API_KEY", "")
            # Clear ollama sentinel if switching from Ollama
            if current_key == "ollama":
                current_key = ""
            api_key = _prompt("Anthropic API key", current_key, secret=True)
            model = _prompt(
                "Model",
                data.get("LOOM_REFLECTION_MODEL", "claude-haiku-4-5-20251001"),
            )
            data["LOOM_REFLECTION_API_KEY"] = api_key or current_key
            data["LOOM_REFLECTION_BASE_URL"] = "https://api.anthropic.com"
            data["LOOM_REFLECTION_MODEL"] = model or "claude-haiku-4-5-20251001"

        elif choice == 2:
            base_url = _prompt(
                "Ollama base URL",
                data.get("LOOM_REFLECTION_BASE_URL", "http://localhost:11434"),
            )
            if base_url and not base_url.startswith(("http://", "https://")):
                base_url = f"http://{base_url}"
            model = _prompt(
                "Model name",
                data.get("LOOM_REFLECTION_MODEL", "qwen3:8b"),
            )
            data["LOOM_REFLECTION_BASE_URL"] = base_url or "http://localhost:11434"
            data["LOOM_REFLECTION_MODEL"] = model or "qwen3:8b"
            data["LOOM_REFLECTION_API_KEY"] = "ollama"

        else:  # choice == 3
            base_url = _prompt("Base URL", data.get("LOOM_REFLECTION_BASE_URL", ""))
            current_key = data.get("LOOM_REFLECTION_API_KEY", "")
            if current_key == "ollama":
                current_key = ""
            api_key = _prompt("API key", current_key, secret=True)
            model = _prompt("Model name", data.get("LOOM_REFLECTION_MODEL", ""))
            if base_url:
                data["LOOM_REFLECTION_BASE_URL"] = base_url
            if api_key:
                data["LOOM_REFLECTION_API_KEY"] = api_key
            if model:
                data["LOOM_REFLECTION_MODEL"] = model

    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return

    _write_env(env_file, data)
    print(f"\nConfig saved to {env_file}")


def main() -> None:
    """Entry point for loom-config."""
    import argparse

    parser = argparse.ArgumentParser(
        description="loom-code: view or edit ~/.loom-code/.env config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  loom-config                         # show current config
  loom-config --edit                  # interactive editor
  loom-config --set KEY VALUE         # set a single key
""",
    )
    parser.add_argument("--edit", action="store_true", help="Interactive config editor")
    parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Set a single config key")
    args = parser.parse_args()

    from loom_mcp.config import ENV_FILE

    if args.set:
        edit(ENV_FILE, args.set[0], args.set[1])
    elif args.edit:
        interactive(ENV_FILE)
    else:
        show(ENV_FILE)


if __name__ == "__main__":
    main()
