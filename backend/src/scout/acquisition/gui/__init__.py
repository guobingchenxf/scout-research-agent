"""Read-only GUI fallback for sources without an API."""

from .reader import FakeGuiReader, GuiError, GuiReader, PlaywrightGuiReader

__all__ = ["FakeGuiReader", "GuiError", "GuiReader", "PlaywrightGuiReader"]
