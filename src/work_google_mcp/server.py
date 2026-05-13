"""FastMCP server setup, tool registration, and stdio entrypoint."""

from __future__ import annotations

import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .auth import assert_pinned_account, build_gmail_service, get_credentials
from .errors import AccountMismatchError
from .tools import gmail as gmail_tools


def _build_service_provider() -> tuple[Any, str]:
    """Lazily load credentials and return (provider, verified_email).

    The provider is a zero-arg callable so tools can be registered before any
    network call happens — useful during testing and during stdio handshakes.
    """
    creds = get_credentials(interactive=False)
    email = assert_pinned_account(creds)
    service = build_gmail_service(creds)

    def provider() -> Any:
        return service

    return provider, email


def create_server() -> FastMCP:
    """Create the FastMCP server, wire up credentials, and register tools."""
    try:
        provider, email = _build_service_provider()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2) from e
    except AccountMismatchError as e:
        print(f"Account pin check failed:\n  {e}", file=sys.stderr)
        raise SystemExit(3) from e
    except Exception as e:
        print(
            f"Failed to start work-google-mcp: {type(e).__name__}: {e}\n"
            "Did you run `work-google-mcp --login`?",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    print(f"work-google-mcp: authenticated as {email}", file=sys.stderr)

    mcp = FastMCP("work_google_mcp")
    gmail_tools.register(mcp, provider)
    return mcp


def run() -> None:
    """Run the server over stdio (the only supported transport in Phase 1)."""
    server = create_server()
    server.run()
