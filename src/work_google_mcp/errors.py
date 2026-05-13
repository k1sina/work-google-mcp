"""Translate Google API errors into actionable strings agents can recover from."""

from __future__ import annotations

from googleapiclient.errors import HttpError


class AccountMismatchError(RuntimeError):
    """Raised when the authenticated account doesn't match the pinned email."""


def handle_google_error(e: Exception) -> str:
    """Convert an exception from a Google API call into a concise, actionable string.

    Returns a string prefixed with "Error:" suitable for returning directly from a tool.
    """
    if isinstance(e, HttpError):
        status = e.resp.status if hasattr(e, "resp") else None
        # Try to extract the API-supplied reason for richer context.
        reason = ""
        try:
            details = e.error_details  # type: ignore[attr-defined]
            if isinstance(details, list) and details:
                reason = f" — {details[0].get('reason') or details[0].get('message') or ''}"
        except Exception:
            pass

        if status == 400:
            return f"Error: Bad request{reason}. Check your query syntax and parameter values."
        if status == 401:
            return (
                "Error: Authentication failed (401). The cached token may be invalid. "
                "Delete the token file and re-run --login."
            )
        if status == 403:
            return (
                f"Error: Permission denied (403){reason}. The granted OAuth scopes may not "
                "cover this operation, or the resource is restricted."
            )
        if status == 404:
            return f"Error: Resource not found (404){reason}. Check the ID."
        if status == 429:
            return (
                "Error: Rate limit exceeded (429). Wait and retry; consider narrowing your query."
            )
        if status and 500 <= status < 600:
            return f"Error: Google API server error ({status}){reason}. Retry later."
        return f"Error: Google API request failed (status {status}){reason}."

    if isinstance(e, AccountMismatchError):
        return f"Error: {e}"

    if isinstance(e, TimeoutError):
        return "Error: Request timed out. Try again."

    return f"Error: {type(e).__name__}: {e}"
