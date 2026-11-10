"""Fixed, LLM-free workflows for stable sources.

RPA is deliberately boring: a URL pattern selects a handler, the handler calls
one known adapter, and the result is a normalized document. If the page shape
changes, the handler fails and the router falls through to GUI or reports an
error; it never guesses.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...models import SourceDocument
from ..api_sources import (
    CrossrefApiSource,
    DocsApiSource,
    GitHubApiSource,
    HuggingFaceMirrorSource,
)


@dataclass
class RpaWorkflow:
    id: str
    description: str
    pattern: str
    handler: Callable[[dict[str, Any]], SourceDocument | None]


class RpaRunner:
    def __init__(self, *, with_defaults: bool = True) -> None:
        self._workflows: dict[str, RpaWorkflow] = {}
        self._crossref = CrossrefApiSource()
        self._github = GitHubApiSource()
        self._hf = HuggingFaceMirrorSource()
        self._docs = DocsApiSource()
        if with_defaults:
            self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(
            RpaWorkflow(
                id="crossref_doi",
                description="Resolve a DOI through Crossref",
                pattern=r"(?:doi\.org/|api\.crossref\.org/works/)",
                handler=self._read_crossref,
            )
        )
        self.register(
            RpaWorkflow(
                id="github_repo",
                description="Read a GitHub repository README",
                pattern=r"github\.com/",
                handler=self._read_github,
            )
        )
        self.register(
            RpaWorkflow(
                id="hf_model_card",
                description="Read a HuggingFace model card through the mirror",
                pattern=r"(?:huggingface\.co/|hf-mirror\.com/)",
                handler=self._read_hf,
            )
        )
        self.register(
            RpaWorkflow(
                id="official_docs",
                description="Read an official documentation page",
                pattern=r"(?:docs\.vllm\.ai|docs\.sglang\.ai|nvidia\.github\.io|langchain-ai\.github\.io|modelcontextprotocol\.io)",
                handler=self._read_docs,
            )
        )

    def register(self, workflow: RpaWorkflow) -> None:
        self._workflows[workflow.id] = workflow

    def match(self, reference: str) -> str | None:
        for workflow in self._workflows.values():
            if re.search(workflow.pattern, reference):
                return workflow.id
        return None

    def run(self, workflow_id: str, params: dict[str, Any]) -> SourceDocument | None:
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            return None
        return workflow.handler(params)

    def search(self, query: str, k: int) -> list[SourceDocument]:
        # Search is API territory; RPA handles fixed lookups, not open queries.
        return []

    def close(self) -> None:
        for source in (self._crossref, self._github, self._hf, self._docs):
            source.close()

    def _read_crossref(self, params: dict[str, Any]) -> SourceDocument | None:
        return self._crossref.read(str(params.get("url", "")))

    def _read_github(self, params: dict[str, Any]) -> SourceDocument | None:
        return self._github.read(str(params.get("url", "")))

    def _read_hf(self, params: dict[str, Any]) -> SourceDocument | None:
        return self._hf.read(str(params.get("url", "")))

    def _read_docs(self, params: dict[str, Any]) -> SourceDocument | None:
        return self._docs.read(str(params.get("url", "")))
