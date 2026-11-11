"""Read-only GUI boundary with allowlist and injection marking."""

from __future__ import annotations

from ..acquisition.gui.reader import GuiError, GuiReader
from ..models import SourceDocument, TrustLevel
from ..policy.allowlist import AllowlistPolicy
from ..policy.injection import InjectionDetector


class GuiSandbox:
    def __init__(
        self,
        allowlist: AllowlistPolicy,
        reader: GuiReader,
        *,
        detector: InjectionDetector | None = None,
        max_chars: int = 20_000,
    ) -> None:
        self.allowlist = allowlist
        self.reader = reader
        self.detector = detector or InjectionDetector()
        self.max_chars = max_chars

    def read(self, url: str) -> SourceDocument | None:
        verdict = self.allowlist.check(url)
        if not verdict.allowed:
            raise GuiError(verdict.reason or "GUI URL denied")
        document = self.reader.read(url)
        if document is None:
            return None
        if len(document.text) > self.max_chars:
            document.text = document.text[: self.max_chars]
        scan = self.detector.scan(document.text)
        if scan.blocked:
            document.trust = TrustLevel.UNTRUSTED
            document.text = self.detector.sanitize(document.text, TrustLevel.UNTRUSTED)
        return document

    def close(self) -> None:
        close = getattr(self.reader, "close", None)
        if callable(close):
            close()
