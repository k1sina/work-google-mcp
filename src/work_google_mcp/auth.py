"""OAuth flow, token persistence, and the account-pin guard."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from .config import (
    CURRENT_SCOPES,
    client_secrets_path,
    ensure_config_dir,
    pinned_email,
    token_path,
)
from .errors import AccountMismatchError


def _load_credentials() -> Credentials | None:
    p = token_path()
    if not p.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(p), CURRENT_SCOPES)
    except (ValueError, json.JSONDecodeError):
        return None


def _save_credentials(creds: Credentials) -> None:
    ensure_config_dir()
    p = token_path()
    p.write_text(creds.to_json())
    with contextlib.suppress(OSError):
        os.chmod(p, 0o600)


def _run_oauth_flow() -> Credentials:
    secrets = client_secrets_path()
    if not secrets.exists():
        raise FileNotFoundError(
            f"OAuth client secrets not found at {secrets}. "
            "Download a Desktop OAuth client JSON from Google Cloud Console "
            "and place it there (see docs/setup.md), or set "
            "WORK_GOOGLE_MCP_CLIENT_SECRETS to its path."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), CURRENT_SCOPES)
    # port=0 picks an unused loopback port; matches the OAuth client's
    # implicit http://127.0.0.1 redirect URI.
    return flow.run_local_server(port=0)


def get_credentials(*, interactive: bool = False) -> Credentials:
    """Load cached credentials, refreshing or re-running the flow as needed.

    Args:
        interactive: If True, the OAuth browser flow is allowed for first login or
            when refresh fails. If False (default — MCP server runtime), missing or
            broken credentials raise instead of blocking on a browser prompt.
    """
    creds = _load_credentials()

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
            return creds
        except Exception as e:
            if not interactive:
                raise RuntimeError(
                    f"Cached token refresh failed ({e}). Run `work-google-mcp --login` "
                    "to re-authorize."
                ) from e

    if not interactive:
        raise RuntimeError(
            "No valid cached credentials. Run `work-google-mcp --login` to authorize."
        )

    creds = _run_oauth_flow()
    _save_credentials(creds)
    return creds


def _fetch_authenticated_email(creds: Credentials) -> str:
    """Call Gmail users.getProfile to learn which account the token belongs to."""
    service: Any = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress")
    if not isinstance(email, str) or not email:
        raise RuntimeError("Gmail getProfile returned no emailAddress.")
    return email


def assert_pinned_account(creds: Credentials) -> str:
    """Verify the credentials belong to the pinned email. Returns the verified email."""
    actual = _fetch_authenticated_email(creds)
    pin = pinned_email()
    if pin and actual.lower() != pin.lower():
        raise AccountMismatchError(
            f"Authenticated as {actual}, but WORK_GOOGLE_MCP_PINNED_EMAIL={pin}. "
            "The cached token belongs to a different Google account. "
            "Delete the token file and re-run --login with the correct account."
        )
    return actual


def build_gmail_service(creds: Credentials) -> Resource:
    """Build a Gmail API client. Discovery cache is disabled to silence stale-cache warnings."""
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def login_command() -> int:
    """Implementation of `work-google-mcp --login`: run the OAuth flow interactively."""
    try:
        creds = get_credentials(interactive=True)
        email = assert_pinned_account(creds)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except AccountMismatchError as e:
        print(f"Authorization succeeded but account check failed:\n  {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1

    pin = pinned_email()
    pin_note = "" if pin else " (no WORK_GOOGLE_MCP_PINNED_EMAIL set — strongly recommended)"
    print(f"Authorized as {email}{pin_note}.")
    print(f"Token cached to {token_path()}.")
    return 0
