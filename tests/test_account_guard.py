"""Unit tests for the account-pin guard and config helpers."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from work_google_mcp import auth, config
from work_google_mcp.errors import AccountMismatchError


class _FakeCreds:
    pass


def test_pinned_email_matches() -> None:
    with (
        patch.dict(os.environ, {"WORK_GOOGLE_MCP_PINNED_EMAIL": "work@example.com"}),
        patch.object(auth, "_fetch_authenticated_email", return_value="work@example.com"),
    ):
        assert auth.assert_pinned_account(_FakeCreds()) == "work@example.com"  # type: ignore[arg-type]


def test_pinned_email_mismatch_raises() -> None:
    with (
        patch.dict(os.environ, {"WORK_GOOGLE_MCP_PINNED_EMAIL": "work@example.com"}),
        patch.object(auth, "_fetch_authenticated_email", return_value="personal@gmail.com"),
        pytest.raises(AccountMismatchError),
    ):
        auth.assert_pinned_account(_FakeCreds())  # type: ignore[arg-type]


def test_pinned_email_case_insensitive() -> None:
    with (
        patch.dict(os.environ, {"WORK_GOOGLE_MCP_PINNED_EMAIL": "Work@Example.com"}),
        patch.object(auth, "_fetch_authenticated_email", return_value="work@example.com"),
    ):
        assert auth.assert_pinned_account(_FakeCreds()) == "work@example.com"  # type: ignore[arg-type]


def test_no_pin_skips_check() -> None:
    with (
        patch.dict(os.environ, {}, clear=False),
        patch.object(auth, "_fetch_authenticated_email", return_value="anyone@gmail.com"),
    ):
        os.environ.pop("WORK_GOOGLE_MCP_PINNED_EMAIL", None)
        assert auth.assert_pinned_account(_FakeCreds()) == "anyone@gmail.com"  # type: ignore[arg-type]


def test_token_path_override(tmp_path: Any) -> None:
    custom = tmp_path / "custom-token.json"
    with patch.dict(os.environ, {"WORK_GOOGLE_MCP_TOKEN_PATH": str(custom)}):
        assert config.token_path() == custom


def test_client_secrets_override(tmp_path: Any) -> None:
    custom = tmp_path / "custom-secrets.json"
    with patch.dict(os.environ, {"WORK_GOOGLE_MCP_CLIENT_SECRETS": str(custom)}):
        assert config.client_secrets_path() == custom
