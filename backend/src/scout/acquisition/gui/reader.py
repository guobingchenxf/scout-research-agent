"""Read-only Playwright fallback.

The GUI path is a last resort. It never clicks, types, submits forms, logs in,
downloads, uploads, or reads the clipboard. It only navigates and extracts the
page title and body text, capped by `max_chars`.
"""

from __future__ import annotations

import hashlib
from typing import Protocol
from urllib.parse import urlparse

from ...models import (
    RetrievalMethod,
    SourceDocument,
    SourceType,
    TrustLevel,
)


class GuiError(Exception):
    pass


class GuiReader(Protocol):
    def read(self, url: str) -> SourceDocument | None: ...


class FakeGuiReader:
    """Test double with a deterministic document."""

    def __init__(self, text: str = "GUI fallback content", title: str = "GUI page") -> None:
        self.text = text
        self.title = title
        self.calls: list[str] = []

    def read(self, url: str) -> SourceDocument | None:
        self.calls.append(url)
        content = f"# {self.title}\n\nSource: {url}\n\n{self.text}\n"
        return SourceDocument(
            id=f"gui:{hashlib.sha256(url.encode()).hexdigest()[:16]}",
            title=self.title,
            url=url,
            source_type=SourceType.WEB,
            trust=TrustLevel.SECONDARY,
            retrieval_method=RetrievalMethod.GUI,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            text=content,
            metadata={"read_only": True},
        )

    def close(self) -> None:
        return None


class PlaywrightGuiReader:
    def __init__(
        self,
        *,
        timeout_ms: int = 20_000,
        max_chars: int = 20_000,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.max_chars = max_chars
        self.allowed_hosts = {host.lower() for host in (allowed_hosts or set())}

    def read(self, url: str) -> SourceDocument | None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise GuiError("GUI fallback only allows https")
        if self.allowed_hosts and (parsed.hostname or "").lower() not in self.allowed_hosts:
            raise GuiError(f"host is not allowed for GUI fallback: {parsed.hostname}")
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError as exc:
            raise GuiError(
                "playwright is not installed; run `pip install -e '.[gui]'` "
                "and `playwright install chromium`"
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    accept_downloads=False,
                    java_script_enabled=True,
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                title = page.title()
                text = page.locator("body").inner_text(timeout=self.timeout_ms)
                content = f"# {title}\n\nSource: {url}\n\n{text[: self.max_chars]}\n"
                return SourceDocument(
                    id=f"gui:{hashlib.sha256(url.encode()).hexdigest()[:16]}",
                    title=title or url,
                    url=url,
                    source_type=SourceType.WEB,
                    trust=TrustLevel.SECONDARY,
                    retrieval_method=RetrievalMethod.GUI,
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                    text=content,
                    metadata={"read_only": True},
                )
            finally:
                browser.close()

    def close(self) -> None:
        return None
