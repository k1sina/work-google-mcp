"""Phase 1 Gmail tools — all read-only.

The MCP tool surface is a thin layer over googleapiclient. We register tools on
the FastMCP server in `register(mcp, service_provider)`, where `service_provider`
is a zero-arg callable returning a Gmail v1 Resource. This indirection lets tests
inject a mock service.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from ..errors import handle_google_error
from ..formatting import (
    ResponseFormat,
    extract_text_and_attachments,
    header_value,
    parse_internal_date,
    to_json,
    truncate,
)

ServiceProvider = Callable[[], Any]


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


class WhoamiInput(_Base):
    pass


class ListLabelsInput(_Base):
    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="'json' for machine-readable, 'markdown' for a human-readable list.",
    )


class SearchMessagesInput(_Base):
    query: str = Field(
        ...,
        description=(
            "Gmail search query. Examples: 'from:alice@example.com is:unread', "
            "'subject:\"Q4 review\" after:2026/01/01', 'has:attachment label:Finance'."
        ),
        min_length=1,
        max_length=1000,
    )
    max_results: int = Field(
        default=25,
        description="Maximum messages to return per page (1-100).",
        ge=1,
        le=100,
    )
    page_token: str | None = Field(
        default=None,
        description="Opaque token from a previous response's next_page_token to fetch the next page.",
    )
    include_spam_trash: bool = Field(
        default=False,
        description="If true, include messages from Spam and Trash.",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="'json' for structured output, 'markdown' for a readable summary.",
    )


class SearchThreadsInput(_Base):
    query: str = Field(..., min_length=1, max_length=1000)
    max_results: int = Field(default=25, ge=1, le=100)
    page_token: str | None = Field(default=None)
    include_spam_trash: bool = Field(default=False)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON)


class GetMessageInput(_Base):
    message_id: str = Field(
        ...,
        description="The Gmail message ID (the `id` field from a search result).",
        min_length=1,
        max_length=200,
    )
    max_body_chars: int = Field(
        default=20000,
        description="Truncate the decoded text body to this many characters (1-200000).",
        ge=1,
        le=200_000,
    )
    include_html: bool = Field(
        default=False,
        description="If true, also include the HTML body (truncated to the same cap).",
    )


class GetThreadInput(_Base):
    thread_id: str = Field(..., min_length=1, max_length=200)
    max_body_chars: int = Field(default=10000, ge=1, le=200_000)
    include_html: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarize_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Lift the most useful header fields into a flat dict for list responses."""
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "snippet": msg.get("snippet"),
        "date": parse_internal_date(msg.get("internalDate")),
        "from": header_value(headers, "From"),
        "to": header_value(headers, "To"),
        "cc": header_value(headers, "Cc"),
        "subject": header_value(headers, "Subject"),
        "label_ids": msg.get("labelIds") or [],
    }


def _full_message(msg: dict[str, Any], max_body_chars: int, include_html: bool) -> dict[str, Any]:
    """Build the full-message response shape used by get_message / get_thread."""
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []
    text, html, attachments = extract_text_and_attachments(payload)

    text_out, text_truncated = truncate(text, max_body_chars)
    out: dict[str, Any] = {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "date": parse_internal_date(msg.get("internalDate")),
        "from": header_value(headers, "From"),
        "to": header_value(headers, "To"),
        "cc": header_value(headers, "Cc"),
        "bcc": header_value(headers, "Bcc"),
        "subject": header_value(headers, "Subject"),
        "label_ids": msg.get("labelIds") or [],
        "snippet": msg.get("snippet"),
        "body_text": text_out,
        "body_text_truncated": text_truncated,
        "attachments": attachments,
    }
    if include_html:
        html_out, html_truncated = truncate(html, max_body_chars)
        out["body_html"] = html_out
        out["body_html_truncated"] = html_truncated
    return out


def _markdown_message_summaries(
    items: list[dict[str, Any]], title: str, next_page_token: str | None
) -> str:
    lines = [f"# {title}", ""]
    if not items:
        lines.append("_No results._")
        return "\n".join(lines)
    for item in items:
        lines.append(f"## {item.get('subject') or '(no subject)'}")
        lines.append(f"- **From**: {item.get('from') or '-'}")
        lines.append(f"- **Date**: {item.get('date') or '-'}")
        lines.append(f"- **ID**: `{item.get('id')}`  **Thread**: `{item.get('thread_id')}`")
        if item.get("snippet"):
            lines.append(f"- {item['snippet']}")
        lines.append("")
    if next_page_token:
        lines.append(f"_More results available — pass `page_token={next_page_token!r}`._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def _read_only_annotations(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )


def register(mcp: FastMCP, service_provider: ServiceProvider) -> None:
    """Register all Phase 1 Gmail tools on the given FastMCP server."""

    @mcp.tool(
        name="gmail_whoami",
        annotations=_read_only_annotations("Gmail: Authenticated Account"),
    )
    async def gmail_whoami(_: WhoamiInput) -> str:
        """Return the email address of the Google account this server is connected to.

        Use this to confirm the agent is acting on the **work** account before
        running anything sensitive. Returns a JSON object:

            {
              "email": str,
              "messages_total": int,
              "threads_total": int,
              "history_id": str
            }
        """
        try:
            svc = service_provider()
            profile = svc.users().getProfile(userId="me").execute()
            return to_json(
                {
                    "email": profile.get("emailAddress"),
                    "messages_total": profile.get("messagesTotal"),
                    "threads_total": profile.get("threadsTotal"),
                    "history_id": profile.get("historyId"),
                }
            )
        except Exception as e:
            return handle_google_error(e)

    @mcp.tool(
        name="gmail_list_labels",
        annotations=_read_only_annotations("Gmail: List Labels"),
    )
    async def gmail_list_labels(params: ListLabelsInput) -> str:
        """List all labels (system + user) in the authenticated mailbox.

        Args:
            params: { response_format: 'json' | 'markdown' }

        Returns:
            JSON:    {"labels": [{"id": str, "name": str, "type": "system"|"user"}, ...]}
            MD:      A two-section list grouped by type.
        """
        try:
            svc = service_provider()
            data = svc.users().labels().list(userId="me").execute()
            labels = [
                {"id": lbl.get("id"), "name": lbl.get("name"), "type": lbl.get("type")}
                for lbl in data.get("labels", [])
            ]
            if params.response_format == ResponseFormat.JSON:
                return to_json({"labels": labels})

            system = [lbl for lbl in labels if lbl["type"] == "system"]
            user = [lbl for lbl in labels if lbl["type"] != "system"]
            lines = ["# Gmail Labels", "", "## System", ""]
            lines += [f"- `{lbl['id']}` — {lbl['name']}" for lbl in system] or ["_none_"]
            lines += ["", "## User", ""]
            lines += [f"- `{lbl['id']}` — {lbl['name']}" for lbl in user] or ["_none_"]
            return "\n".join(lines)
        except Exception as e:
            return handle_google_error(e)

    @mcp.tool(
        name="gmail_search_messages",
        annotations=_read_only_annotations("Gmail: Search Messages"),
    )
    async def gmail_search_messages(params: SearchMessagesInput) -> str:
        """Search messages using Gmail's query syntax.

        Returns header-level summaries (no message bodies). Call `gmail_get_message`
        with an ID from the results to read the full text of a specific message.

        Args:
            params:
                - query (str): Gmail search query (see Gmail's search operators).
                - max_results (int 1-100, default 25)
                - page_token (str | None): opaque token for the next page
                - include_spam_trash (bool, default false)
                - response_format ('json' | 'markdown')

        Returns:
            JSON:
                {
                  "result_size_estimate": int,
                  "count": int,
                  "next_page_token": str | null,
                  "messages": [{"id", "thread_id", "subject", "from", "to", "cc",
                                "date", "snippet", "label_ids"}, ...]
                }
        """
        try:
            svc = service_provider()
            req_args: dict[str, Any] = {
                "userId": "me",
                "q": params.query,
                "maxResults": params.max_results,
                "includeSpamTrash": params.include_spam_trash,
            }
            if params.page_token:
                req_args["pageToken"] = params.page_token
            listing = svc.users().messages().list(**req_args).execute()
            ids = [m["id"] for m in listing.get("messages", []) if m.get("id")]

            # Fetch each message's metadata. Gmail has no bulk-get, so this is N calls.
            summaries: list[dict[str, Any]] = []
            for mid in ids:
                msg = (
                    svc.users()
                    .messages()
                    .get(
                        userId="me",
                        id=mid,
                        format="metadata",
                        metadataHeaders=["From", "To", "Cc", "Subject", "Date"],
                    )
                    .execute()
                )
                summaries.append(_summarize_message(msg))

            next_token = listing.get("nextPageToken")
            payload = {
                "result_size_estimate": listing.get("resultSizeEstimate", 0),
                "count": len(summaries),
                "next_page_token": next_token,
                "messages": summaries,
            }
            if params.response_format == ResponseFormat.JSON:
                return to_json(payload)
            return _markdown_message_summaries(summaries, f"Search: `{params.query}`", next_token)
        except Exception as e:
            return handle_google_error(e)

    @mcp.tool(
        name="gmail_search_threads",
        annotations=_read_only_annotations("Gmail: Search Threads"),
    )
    async def gmail_search_threads(params: SearchThreadsInput) -> str:
        """Search threads matching a Gmail query.

        Returns the thread ID, a snippet of the most recent message, and counts.
        Use `gmail_get_thread` to retrieve full messages from a thread.

        Returns (JSON):
            {
              "result_size_estimate": int,
              "count": int,
              "next_page_token": str | null,
              "threads": [{"id", "snippet", "history_id"}, ...]
            }
        """
        try:
            svc = service_provider()
            req_args: dict[str, Any] = {
                "userId": "me",
                "q": params.query,
                "maxResults": params.max_results,
                "includeSpamTrash": params.include_spam_trash,
            }
            if params.page_token:
                req_args["pageToken"] = params.page_token
            listing = svc.users().threads().list(**req_args).execute()

            threads = [
                {
                    "id": t.get("id"),
                    "snippet": t.get("snippet"),
                    "history_id": t.get("historyId"),
                }
                for t in listing.get("threads", [])
            ]
            next_token = listing.get("nextPageToken")
            payload = {
                "result_size_estimate": listing.get("resultSizeEstimate", 0),
                "count": len(threads),
                "next_page_token": next_token,
                "threads": threads,
            }
            if params.response_format == ResponseFormat.JSON:
                return to_json(payload)

            lines = [f"# Threads matching `{params.query}`", ""]
            if not threads:
                lines.append("_No results._")
            else:
                for t in threads:
                    lines.append(f"- `{t['id']}` — {t.get('snippet') or '(no snippet)'}")
            if next_token:
                lines.append("")
                lines.append(f"_More results — pass `page_token={next_token!r}`._")
            return "\n".join(lines)
        except Exception as e:
            return handle_google_error(e)

    @mcp.tool(
        name="gmail_get_message",
        annotations=_read_only_annotations("Gmail: Get Message"),
    )
    async def gmail_get_message(params: GetMessageInput) -> str:
        """Fetch a single message by ID with decoded body and attachment metadata.

        Attachments are NOT downloaded in Phase 1 — only their filenames, MIME
        types, and sizes are returned.

        Returns (JSON):
            {
              "id", "thread_id", "date", "from", "to", "cc", "bcc", "subject",
              "label_ids", "snippet",
              "body_text", "body_text_truncated",
              "body_html"?, "body_html_truncated"?,
              "attachments": [{"filename", "mime_type", "size", "attachment_id"}, ...]
            }
        """
        try:
            svc = service_provider()
            msg = (
                svc.users()
                .messages()
                .get(userId="me", id=params.message_id, format="full")
                .execute()
            )
            return to_json(_full_message(msg, params.max_body_chars, params.include_html))
        except Exception as e:
            return handle_google_error(e)

    @mcp.tool(
        name="gmail_get_thread",
        annotations=_read_only_annotations("Gmail: Get Thread"),
    )
    async def gmail_get_thread(params: GetThreadInput) -> str:
        """Fetch a single thread by ID with all messages, ordered oldest-first.

        Each per-message body is truncated to `max_body_chars` (default 10000)
        independently. Use `gmail_get_message` for a single message with a higher cap.

        Returns (JSON):
            {
              "id": str,
              "history_id": str,
              "messages": [<same shape as gmail_get_message>, ...]
            }
        """
        try:
            svc = service_provider()
            thread = (
                svc.users().threads().get(userId="me", id=params.thread_id, format="full").execute()
            )
            messages = [
                _full_message(m, params.max_body_chars, params.include_html)
                for m in thread.get("messages", [])
            ]
            return to_json(
                {
                    "id": thread.get("id"),
                    "history_id": thread.get("historyId"),
                    "messages": messages,
                }
            )
        except Exception as e:
            return handle_google_error(e)
