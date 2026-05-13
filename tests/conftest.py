"""Shared test fixtures: a hand-rolled mock of the Gmail API client."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

import pytest


class _Method:
    """Wraps a fixture function so calling it returns an object with `.execute()`."""

    def __init__(self, fn: Callable[..., Any]) -> None:
        self._fn = fn

    def __call__(self, **kwargs: Any) -> _Executable:
        return _Executable(self._fn, kwargs)


class _Executable:
    def __init__(self, fn: Callable[..., Any], kwargs: dict[str, Any]) -> None:
        self._fn = fn
        self._kwargs = kwargs

    def execute(self) -> Any:
        return self._fn(**self._kwargs)


class FakeMessages:
    def __init__(self, store: FakeGmailStore) -> None:
        self._store = store
        self.list = _Method(self._list)
        self.get = _Method(self._get)

    def _list(
        self,
        userId: str,
        q: str = "",
        maxResults: int = 100,
        pageToken: str | None = None,
        includeSpamTrash: bool = False,
    ) -> dict[str, Any]:
        msgs = [{"id": m["id"], "threadId": m["threadId"]} for m in self._store.messages]
        return {
            "messages": msgs[:maxResults],
            "resultSizeEstimate": len(msgs),
            "nextPageToken": None,
        }

    def _get(
        self,
        userId: str,
        id: str,
        format: str = "full",
        metadataHeaders: list[str] | None = None,
    ) -> dict[str, Any]:
        for m in self._store.messages:
            if m["id"] == id:
                return m
        raise KeyError(id)


class FakeThreads:
    def __init__(self, store: FakeGmailStore) -> None:
        self._store = store
        self.list = _Method(self._list)
        self.get = _Method(self._get)

    def _list(
        self,
        userId: str,
        q: str = "",
        maxResults: int = 100,
        pageToken: str | None = None,
        includeSpamTrash: bool = False,
    ) -> dict[str, Any]:
        threads = [
            {"id": t["id"], "snippet": t.get("snippet"), "historyId": t.get("historyId")}
            for t in self._store.threads
        ]
        return {
            "threads": threads[:maxResults],
            "resultSizeEstimate": len(threads),
            "nextPageToken": None,
        }

    def _get(self, userId: str, id: str, format: str = "full") -> dict[str, Any]:
        for t in self._store.threads:
            if t["id"] == id:
                return t
        raise KeyError(id)


class FakeLabels:
    def __init__(self, store: FakeGmailStore) -> None:
        self._store = store
        self.list = _Method(self._list)

    def _list(self, userId: str) -> dict[str, Any]:
        return {"labels": self._store.labels}


class FakeUsers:
    def __init__(self, store: FakeGmailStore) -> None:
        self._store = store
        self._messages = FakeMessages(store)
        self._threads = FakeThreads(store)
        self._labels = FakeLabels(store)
        self.getProfile = _Method(self._get_profile)

    def messages(self) -> FakeMessages:
        return self._messages

    def threads(self) -> FakeThreads:
        return self._threads

    def labels(self) -> FakeLabels:
        return self._labels

    def _get_profile(self, userId: str) -> dict[str, Any]:
        return self._store.profile


class FakeGmailService:
    def __init__(self, store: FakeGmailStore) -> None:
        self._users = FakeUsers(store)

    def users(self) -> FakeUsers:
        return self._users


class FakeGmailStore:
    """Hand-built corpus of Gmail data for tests."""

    def __init__(self) -> None:
        self.profile: dict[str, Any] = {
            "emailAddress": "work-user@example.com",
            "messagesTotal": 2,
            "threadsTotal": 1,
            "historyId": "12345",
        }
        self.labels: list[dict[str, Any]] = [
            {"id": "INBOX", "name": "INBOX", "type": "system"},
            {"id": "UNREAD", "name": "UNREAD", "type": "system"},
            {"id": "Label_99", "name": "Finance", "type": "user"},
        ]
        body_text = base64.urlsafe_b64encode(b"Hello from the test mailbox.\nSecond line.").decode(
            "ascii"
        )
        body_html = base64.urlsafe_b64encode(b"<p>Hello from the test mailbox.</p>").decode("ascii")
        self.messages: list[dict[str, Any]] = [
            {
                "id": "m1",
                "threadId": "t1",
                "snippet": "Hello from the test mailbox.",
                "internalDate": "1715000000000",
                "labelIds": ["INBOX", "UNREAD"],
                "payload": {
                    "headers": [
                        {"name": "From", "value": "alice@example.com"},
                        {"name": "To", "value": "work-user@example.com"},
                        {"name": "Subject", "value": "Test message"},
                        {"name": "Date", "value": "Mon, 06 May 2026 12:00:00 +0000"},
                    ],
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": body_text, "size": 50},
                        },
                        {
                            "mimeType": "text/html",
                            "body": {"data": body_html, "size": 35},
                        },
                        {
                            "mimeType": "application/pdf",
                            "filename": "report.pdf",
                            "body": {"attachmentId": "att1", "size": 12345},
                        },
                    ],
                },
            },
            {
                "id": "m2",
                "threadId": "t1",
                "snippet": "Re: Test message",
                "internalDate": "1715003600000",
                "labelIds": ["INBOX"],
                "payload": {
                    "headers": [
                        {"name": "From", "value": "work-user@example.com"},
                        {"name": "To", "value": "alice@example.com"},
                        {"name": "Subject", "value": "Re: Test message"},
                    ],
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(b"Thanks, got it.").decode("ascii"),
                        "size": 14,
                    },
                },
            },
        ]
        self.threads: list[dict[str, Any]] = [
            {
                "id": "t1",
                "snippet": "Re: Test message",
                "historyId": "12345",
                "messages": self.messages,
            }
        ]


@pytest.fixture
def gmail_store() -> FakeGmailStore:
    return FakeGmailStore()


@pytest.fixture
def gmail_service(gmail_store: FakeGmailStore) -> FakeGmailService:
    return FakeGmailService(gmail_store)
