"""Acquisition layer: API first, MCP, RPA, then read-only GUI."""

from .api_sources import (
    ApiSource,
    CrossrefApiSource,
    DocsApiSource,
    GitHubApiSource,
    HuggingFaceMirrorSource,
    default_api_sources,
)
from .router import AcquisitionRouter

__all__ = [
    "AcquisitionRouter",
    "ApiSource",
    "CrossrefApiSource",
    "DocsApiSource",
    "GitHubApiSource",
    "HuggingFaceMirrorSource",
    "default_api_sources",
]
