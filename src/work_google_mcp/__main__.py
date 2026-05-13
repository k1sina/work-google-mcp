"""Entrypoint: `python -m work_google_mcp` and the `work-google-mcp` console script."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="work-google-mcp",
        description=(
            "MCP server for a Google account isolated from your primary one. "
            "Default action: run the MCP server over stdio."
        ),
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Run the OAuth flow interactively (opens a browser). Exits after authorizing.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"work-google-mcp {__version__}",
    )
    args = parser.parse_args(argv)

    if args.login:
        from .auth import login_command

        return login_command()

    # Default: run the MCP server. Imported lazily so --login and --help don't
    # require valid credentials.
    from .server import run

    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
