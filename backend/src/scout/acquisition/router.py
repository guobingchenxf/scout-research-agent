"""Capability-based acquisition routing: API → MCP → RPA → GUI."""

from __future__ import annotations

import hashlib
from typing import Any

from ..config import ScoutConfig
from ..models import (
    AcquisitionResult,
    RetrievalMethod,
    SourceDocument,
    SourceType,
    TrustLevel,
)
from ..policy.allowlist import AllowlistPolicy
from .api_sources import ApiSource, default_api_sources


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AcquisitionRouter:
    def __init__(
        self,
        config: ScoutConfig,
        *,
        api_sources: list[ApiSource] | None = None,
        mcp_client: Any | None = None,
        rpa_runner: Any | None = None,
        gui_reader: Any | None = None,
    ) -> None:
        self.config = config
        self.api_sources = api_sources if api_sources is not None else default_api_sources(config)
        self.mcp_client = mcp_client
        self.rpa_runner = rpa_runner
        self.gui_reader = gui_reader
        self.allowlist = AllowlistPolicy(
            config.source_allowlist,
            verify_dns=config.verify_dns,
            allow_http_local=config.allow_http_local,
        )

    def search(
        self,
        query: str,
        *,
        k: int = 8,
        sources: list[str] | None = None,
    ) -> AcquisitionResult:
        errors: list[str] = []
        for source in self.api_sources:
            try:
                documents = self._filter(source.search(query, k), sources)
            except Exception as exc:  # noqa: BLE001 - try the next path
                errors.append(f"{source.name}: {exc}")
                continue
            if documents:
                return AcquisitionResult(
                    documents=documents,
                    method=RetrievalMethod.API,
                )

        if self.mcp_client is not None:
            for tool in ("web_search", "search"):
                try:
                    output = self.mcp_client.call_tool(tool, {"query": query, "k": k})
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"mcp:{tool}: {exc}")
                    continue
                documents = self._filter(self._documents_from_mcp(output), sources)
                if documents:
                    return AcquisitionResult(
                        documents=documents,
                        method=RetrievalMethod.MCP,
                    )

        if self.rpa_runner is not None:
            try:
                documents = self._filter(self.rpa_runner.search(query, k), sources)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"rpa: {exc}")
                documents = []
            if documents:
                return AcquisitionResult(
                    documents=documents,
                    method=RetrievalMethod.RPA,
                )

        return AcquisitionResult(
            error="; ".join(errors) or "no acquisition source returned results",
        )

    def read(self, source_ref: str, locator: str | None = None) -> AcquisitionResult:
        if not self._allowed(source_ref):
            return AcquisitionResult(
                policy_verdict="denied",
                error=f"source is outside the allowlist: {source_ref}",
            )

        errors: list[str] = []
        for source in self.api_sources:
            if not source.supports(source_ref):
                continue
            try:
                document = source.read(source_ref)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source.name}: {exc}")
                continue
            if document is not None:
                return AcquisitionResult(
                    documents=[document],
                    method=RetrievalMethod.API,
                )

        if self.mcp_client is not None:
            for tool in ("fetch", "read_url"):
                try:
                    output = self.mcp_client.call_tool(tool, {"url": source_ref})
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"mcp:{tool}: {exc}")
                    continue
                documents = self._documents_from_mcp(output, fallback_url=source_ref)
                if documents:
                    return AcquisitionResult(
                        documents=documents,
                        method=RetrievalMethod.MCP,
                    )

        if self.rpa_runner is not None:
            try:
                workflow_id = self.rpa_runner.match(source_ref)
                if workflow_id:
                    document = self.rpa_runner.run(workflow_id, {"url": source_ref})
                    if document is not None:
                        return AcquisitionResult(
                            documents=[document],
                            method=RetrievalMethod.RPA,
                        )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"rpa: {exc}")

        if self.gui_reader is not None:
            try:
                document = self.gui_reader.read(source_ref)
                if document is not None:
                    return AcquisitionResult(
                        documents=[document],
                        method=RetrievalMethod.GUI,
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"gui: {exc}")

        return AcquisitionResult(
            error="; ".join(errors) or f"no acquisition source supports: {source_ref}",
        )

    def close(self) -> None:
        for source in self.api_sources:
            close = getattr(source, "close", None)
            if callable(close):
                close()
        for client in (self.mcp_client, self.rpa_runner, self.gui_reader):
            close = getattr(client, "close", None)
            if callable(close):
                close()

    # ------------------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        return self.allowlist.check(url).allowed

    def _filter(
        self,
        documents: list[SourceDocument],
        sources: list[str] | None,
    ) -> list[SourceDocument]:
        if not sources:
            return documents
        wanted = {str(item) for item in sources}
        return [doc for doc in documents if doc.source_type.value in wanted]

    def _documents_from_mcp(
        self, output: Any, *, fallback_url: str = ""
    ) -> list[SourceDocument]:
        if isinstance(output, SourceDocument):
            return [output]
        if isinstance(output, dict):
            if "documents" in output and isinstance(output["documents"], list):
                return [
                    SourceDocument.model_validate(item)
                    for item in output["documents"]
                    if isinstance(item, dict)
                ]
            text = output.get("text") or output.get("content")
            if isinstance(text, list):
                text = "\n".join(
                    str(item.get("text", item)) if isinstance(item, dict) else str(item)
                    for item in text
                )
            if text:
                url = str(output.get("url") or fallback_url)
                title = str(output.get("title") or url or "MCP result")
                body = f"# {title}\n\nSource: {url}\n\n{text}\n"
                return [
                    SourceDocument(
                        id=f"mcp:{_hash(body)[:16]}",
                        title=title,
                        url=url,
                        source_type=SourceType.WEB,
                        trust=TrustLevel.SECONDARY,
                        retrieval_method=RetrievalMethod.MCP,
                        content_hash=_hash(body),
                        text=body,
                    )
                ]
        if isinstance(output, list):
            documents: list[SourceDocument] = []
            for item in output:
                documents.extend(
                    self._documents_from_mcp(item, fallback_url=fallback_url)
                )
            return documents
        return []
