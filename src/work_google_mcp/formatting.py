"""Shared response-formatting helpers."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ResponseFormat(StrEnum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


def to_json(data: Any) -> str:
    """Stable JSON encoding for tool outputs."""
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)


def parse_internal_date(internal_date_ms: str | int | None) -> str | None:
    """Convert Gmail's `internalDate` (millis since epoch) to ISO-8601 UTC."""
    if internal_date_ms is None:
        return None
    try:
        ms = int(internal_date_ms)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def header_value(headers: list[dict[str, str]], name: str) -> str | None:
    """Look up a header value case-insensitively from a Gmail headers list."""
    target = name.lower()
    for h in headers:
        if h.get("name", "").lower() == target:
            return h.get("value")
    return None


def decode_body_data(data: str | None) -> str:
    """Decode Gmail's URL-safe base64 body data into a UTF-8 string."""
    if not data:
        return ""
    try:
        raw = base64.urlsafe_b64decode(data.encode("ascii"))
    except Exception:
        return ""
    return raw.decode("utf-8", errors="replace")


def extract_text_and_attachments(
    payload: dict[str, Any] | None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Walk a Gmail message payload and pull out the best text + attachment list.

    Returns:
        (text_plain, text_html, attachments)

        attachments: list of {filename, mime_type, size, attachment_id}
    """
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[dict[str, Any]] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        filename = part.get("filename") or ""
        body = part.get("body", {}) or {}
        attachment_id = body.get("attachmentId")
        data = body.get("data")

        if filename and (attachment_id or body.get("size", 0) > 0):
            attachments.append(
                {
                    "filename": filename,
                    "mime_type": mime,
                    "size": body.get("size"),
                    "attachment_id": attachment_id,
                }
            )
        elif mime == "text/plain" and data:
            text_parts.append(decode_body_data(data))
        elif mime == "text/html" and data:
            html_parts.append(decode_body_data(data))

        for sub in part.get("parts", []) or []:
            walk(sub)

    if payload:
        walk(payload)

    return "\n".join(text_parts), "\n".join(html_parts), attachments


def truncate(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate text to max_chars. Returns (text, was_truncated)."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[:max_chars] + f"\n\n[...truncated, {len(text) - max_chars} more chars]", True
