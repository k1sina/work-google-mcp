"""Phase 1 Gmail tools — all read-only.

Tools are registered on a FastMCP server via `register(mcp, service_provider)`,
where `service_provider` is a zero-arg callable returning a Gmail v1 client.
This indirection lets tests inject a mock service.

Tool arguments use the canonical FastMCP pattern: individual function arguments
annotated with ``Annotated[T, Field(...)]``. FastMCP exposes each one as a
top-level field in the tool's input schema. (A single ``params: BaseModel``
argument nests under ``params`` instead, which we don't want.)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

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


# Reusable Annotated aliases — declare once, reference per-tool.
_QueryArg = Annotated[
    str,
    Field(
        description=(
            "Gmail search query. Examples: 'from:alice@example.com is:unread', "
            "'subject:\"Q4 review\" after:2026/01/01', 'has:attachment label:Finance'."
        ),
        min_length=1,
        max_length=1000,
    ),
]
_MaxResultsArg = Annotated[
    int,
    Field(description="Maximum results per page (1-100).", ge=1, le=100),
]
_PageTokenArg = Annotated[
    str | None,
    Field(
        default=None,
        description="Opaque token from a previous response's next_page_token to fetch the next page.",
    ),
]
_IncludeSpamTrashArg = Annotated[
    bool,
    Field(default=False, description="If true, include messages from Spam and Trash."),
]
_ResponseFormatArg = Annotated[
    ResponseFormat,
    Field(
        default=ResponseFormat.JSON,
        description="'json' for structured output, 'markdown' for a readable summary.",
    ),
]
_MessageIdArg = Annotated[
    str,
    Field(
        description="The Gmail message ID (the `id` field from a search result).",
        min_length=1,
        max_length=200,
    ),
]
_ThreadIdArg = Annotated[
    str,
    Field(description="The Gmail thread ID.", min_length=1, max_length=200),
]
_MaxBodyCharsArg = Annotated[
    int,
    Field(
        description="Truncate the decoded body to this many characters (1-200000).",
        ge=1,
        le=200_000,
    ),
]
_IncludeHtmlArg = Annotated[
    bool,
    Field(default=False, description="If true, also return the HTML body (same cap)."),
]


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


def _read_only_annotations(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, service_provider: ServiceProvider) -> None:
    """Register all Phase 1 Gmail tools on the given FastMCP server."""

    @mcp.tool(
        name="gmail_whoami",
        annotations=_read_only_annotations("Gmail: Authenticated Account"),
    )
    async def gmail_whoami() -> str:
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
    async def gmail_list_labels(response_format: _ResponseFormatArg = ResponseFormat.JSON) -> str:
        """List all labels (system + user) in the authenticated mailbox.

        Returns:
            JSON: {"labels": [{"id": str, "name": str, "type": "system"|"user"}, ...]}
            Markdown: a two-section list grouped by type.
        """
        try:
            svc = service_provider()
            data = svc.users().labels().list(userId="me").execute()
            labels = [
                {"id": lbl.get("id"), "name": lbl.get("name"), "type": lbl.get("type")}
                for lbl in data.get("labels", [])
            ]
            if response_format == ResponseFormat.JSON:
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
    async def gmail_search_messages(
        query: _QueryArg,
        max_results: _MaxResultsArg = 25,
        page_token: _PageTokenArg = None,
        include_spam_trash: _IncludeSpamTrashArg = False,
        response_format: _ResponseFormatArg = ResponseFormat.JSON,
    ) -> str:
        """Search messages using Gmail's query syntax.

        Returns header-level summaries (no message bodies). Call `gmail_get_message`
        with an ID from the results to read the full text of a specific message.

        Args:
            query: Gmail search query (e.g. 'from:alice is:unread').
            max_results: 1-100, default 25.
            page_token: Opaque token from a previous response's next_page_token.
            include_spam_trash: If true, include Spam and Trash.
            response_format: 'json' or 'markdown'.

        Returns (JSON):
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
                "q": query,
                "maxResults": max_results,
                "includeSpamTrash": include_spam_trash,
            }
            if page_token:
                req_args["pageToken"] = page_token
            listing = svc.users().messages().list(**req_args).execute()
            ids = [m["id"] for m in listing.get("messages", []) if m.get("id")]

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
            if response_format == ResponseFormat.JSON:
                return to_json(payload)
            return _markdown_message_summaries(summaries, f"Search: `{query}`", next_token)
        except Exception as e:
            return handle_google_error(e)

    @mcp.tool(
        name="gmail_search_threads",
        annotations=_read_only_annotations("Gmail: Search Threads"),
    )
    async def gmail_search_threads(
        query: _QueryArg,
        max_results: _MaxResultsArg = 25,
        page_token: _PageTokenArg = None,
        include_spam_trash: _IncludeSpamTrashArg = False,
        response_format: _ResponseFormatArg = ResponseFormat.JSON,
    ) -> str:
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
                "q": query,
                "maxResults": max_results,
                "includeSpamTrash": include_spam_trash,
            }
            if page_token:
                req_args["pageToken"] = page_token
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
            if response_format == ResponseFormat.JSON:
                return to_json(payload)

            lines = [f"# Threads matching `{query}`", ""]
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
    async def gmail_get_message(
        message_id: _MessageIdArg,
        max_body_chars: _MaxBodyCharsArg = 20000,
        include_html: _IncludeHtmlArg = False,
    ) -> str:
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
            msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
            return to_json(_full_message(msg, max_body_chars, include_html))
        except Exception as e:
            return handle_google_error(e)

    @mcp.tool(
        name="gmail_get_thread",
        annotations=_read_only_annotations("Gmail: Get Thread"),
    )
    async def gmail_get_thread(
        thread_id: _ThreadIdArg,
        max_body_chars: _MaxBodyCharsArg = 10000,
        include_html: _IncludeHtmlArg = False,
    ) -> str:
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
            thread = svc.users().threads().get(userId="me", id=thread_id, format="full").execute()
            messages = [
                _full_message(m, max_body_chars, include_html) for m in thread.get("messages", [])
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
