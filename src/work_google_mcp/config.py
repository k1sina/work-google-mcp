"""Configuration: paths, scopes, and environment variable handling."""

from __future__ import annotations

import os
from pathlib import Path

# OAuth scopes per phase. Phase 1 is Gmail read-only. Later phases extend this list.
SCOPES_PHASE_1: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Current scopes the server requests. Bump to include later phases as they ship.
CURRENT_SCOPES: list[str] = SCOPES_PHASE_1


def _default_config_dir() -> Path:
    """Return ~/.config/work-google-mcp, respecting XDG_CONFIG_HOME if set."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "work-google-mcp"


def client_secrets_path() -> Path:
    """Resolve the path to the OAuth client secrets JSON."""
    override = os.environ.get("WORK_GOOGLE_MCP_CLIENT_SECRETS")
    if override:
        return Path(override).expanduser()
    return _default_config_dir() / "client_secrets.json"


def token_path() -> Path:
    """Resolve the path where the cached OAuth token is persisted."""
    override = os.environ.get("WORK_GOOGLE_MCP_TOKEN_PATH")
    if override:
        return Path(override).expanduser()
    return _default_config_dir() / "token.json"


def pinned_email() -> str | None:
    """The email the authenticated account MUST match, or None to skip the check."""
    value = os.environ.get("WORK_GOOGLE_MCP_PINNED_EMAIL", "").strip()
    return value or None


def ensure_config_dir() -> Path:
    """Create the config dir with 0700 permissions if missing."""
    d = _default_config_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d
