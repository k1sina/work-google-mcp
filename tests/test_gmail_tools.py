"""End-to-end tests for Phase 1 Gmail tools, using the FakeGmailService fixture."""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from work_google_mcp.tools import gmail as gmail_tools


@pytest.fixture
def mcp_with_gmail(gmail_service: Any) -> FastMCP:
    mcp = FastMCP("test_work_google_mcp")
    gmail_tools.register(mcp, lambda: gmail_service)
    return mcp


async def _call_tool(mcp: FastMCP, name: str, args: dict[str, Any]) -> str:
    result = await mcp.call_tool(name, args)
    # FastMCP.call_tool returns a tuple of (content_list, structured) in newer
    # versions; older versions return just the content list. Normalize both.
    content = result[0] if isinstance(result, tuple) else result
    return content[0].text  # type: ignore[no-any-return]


async def test_whoami_returns_email(mcp_with_gmail: FastMCP) -> None:
    out = json.loads(await _call_tool(mcp_with_gmail, "gmail_whoami", {}))
    assert out["email"] == "work-user@example.com"
    assert out["messages_total"] == 2


async def test_list_labels_json(mcp_with_gmail: FastMCP) -> None:
    out = json.loads(
        await _call_tool(mcp_with_gmail, "gmail_list_labels", {"response_format": "json"})
    )
    names = {lbl["name"] for lbl in out["labels"]}
    assert {"INBOX", "UNREAD", "Finance"} <= names


async def test_list_labels_markdown(mcp_with_gmail: FastMCP) -> None:
    out = await _call_tool(mcp_with_gmail, "gmail_list_labels", {"response_format": "markdown"})
    assert "# Gmail Labels" in out
    assert "Finance" in out


async def test_search_messages_returns_summaries(mcp_with_gmail: FastMCP) -> None:
    out = json.loads(
        await _call_tool(
            mcp_with_gmail,
            "gmail_search_messages",
            {"query": "is:unread", "max_results": 10},
        )
    )
    assert out["count"] == 2
    assert {m["id"] for m in out["messages"]} == {"m1", "m2"}
    assert out["messages"][0]["subject"] == "Test message"
    assert out["messages"][0]["from"] == "alice@example.com"
    # No body in search summaries.
    assert "body_text" not in out["messages"][0]


async def test_search_threads(mcp_with_gmail: FastMCP) -> None:
    out = json.loads(
        await _call_tool(
            mcp_with_gmail,
            "gmail_search_threads",
            {"query": "is:unread", "max_results": 10},
        )
    )
    assert out["count"] == 1
    assert out["threads"][0]["id"] == "t1"


async def test_get_message_decodes_body_and_lists_attachments(
    mcp_with_gmail: FastMCP,
) -> None:
    out = json.loads(
        await _call_tool(
            mcp_with_gmail,
            "gmail_get_message",
            {"message_id": "m1", "max_body_chars": 1000},
        )
    )
    assert out["id"] == "m1"
    assert "Hello from the test mailbox." in out["body_text"]
    assert out["body_text_truncated"] is False
    assert "body_html" not in out  # not requested
    assert len(out["attachments"]) == 1
    assert out["attachments"][0]["filename"] == "report.pdf"
    assert out["attachments"][0]["size"] == 12345
    assert out["attachments"][0]["attachment_id"] == "att1"


async def test_get_message_truncates_body(mcp_with_gmail: FastMCP) -> None:
    out = json.loads(
        await _call_tool(
            mcp_with_gmail,
            "gmail_get_message",
            {"message_id": "m1", "max_body_chars": 5},
        )
    )
    assert out["body_text_truncated"] is True
    assert "[...truncated" in out["body_text"]


async def test_get_message_html_when_requested(mcp_with_gmail: FastMCP) -> None:
    out = json.loads(
        await _call_tool(
            mcp_with_gmail,
            "gmail_get_message",
            {"message_id": "m1", "max_body_chars": 1000, "include_html": True},
        )
    )
    assert "<p>Hello" in out["body_html"]


async def test_get_thread_returns_all_messages(mcp_with_gmail: FastMCP) -> None:
    out = json.loads(
        await _call_tool(
            mcp_with_gmail,
            "gmail_get_thread",
            {"thread_id": "t1", "max_body_chars": 1000},
        )
    )
    assert out["id"] == "t1"
    assert len(out["messages"]) == 2
    assert out["messages"][1]["subject"] == "Re: Test message"


async def test_invalid_arg_constraints(mcp_with_gmail: FastMCP) -> None:
    """FastMCP/Pydantic should reject out-of-range arguments."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await mcp_with_gmail.call_tool(
            "gmail_search_messages",
            {"query": "x", "max_results": 999},  # > 100, violates ge/le
        )
