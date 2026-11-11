from __future__ import annotations

from typing import Any

from scout.acquisition.gui.reader import FakeGuiReader
from scout.acquisition.mcp_client import MockMcpClient
from scout.acquisition.router import AcquisitionRouter
from scout.config import ScoutConfig
from scout.models import RetrievalMethod, SourceDocument


class FakeApiSource:
    name = "fake-api"

    def __init__(
        self,
        document: SourceDocument | None = None,
        search_documents: list[SourceDocument] | None = None,
    ) -> None:
        self.document = document
        self.search_documents = search_documents or []

    def supports(self, url: str) -> bool:
        return url.startswith("https://api.example.com/")

    def search(self, query: str, k: int) -> list[SourceDocument]:
        return self.search_documents

    def read(self, url: str) -> SourceDocument | None:
        return self.document

    def close(self) -> None:
        return None


class FakeRpaRunner:
    def __init__(self, document: SourceDocument) -> None:
        self.document = document

    def match(self, reference: str) -> str | None:
        return "fixed_workflow" if "rpa.example.com" in reference else None

    def run(self, workflow_id: str, params: dict[str, Any]) -> SourceDocument:
        return self.document

    def search(self, query: str, k: int) -> list[SourceDocument]:
        return []

    def close(self) -> None:
        return None


def _config() -> ScoutConfig:
    return ScoutConfig(
        source_allowlist=(
            "api.example.com",
            "mcp.example.com",
            "rpa.example.com",
            "gui.example.com",
        ),
        verify_dns=False,
    )


def test_read_prefers_api(sample_documents) -> None:
    document = sample_documents[0]
    router = AcquisitionRouter(
        _config(),
        api_sources=[FakeApiSource(document=document)],
        mcp_client=MockMcpClient(),
        gui_reader=FakeGuiReader(),
    )
    result = router.read("https://api.example.com/doc")
    assert result.method == RetrievalMethod.API
    assert result.documents[0].id == document.id


def test_read_falls_back_to_mcp(sample_documents) -> None:
    router = AcquisitionRouter(
        _config(),
        api_sources=[FakeApiSource(document=None)],
        mcp_client=MockMcpClient(
            {"fetch": lambda args: {"text": "mcp body", "url": args["url"], "title": "MCP"}}
        ),
    )
    result = router.read("https://mcp.example.com/doc")
    assert result.method == RetrievalMethod.MCP
    assert result.documents[0].text


def test_read_falls_back_to_rpa(sample_documents) -> None:
    router = AcquisitionRouter(
        _config(),
        api_sources=[FakeApiSource(document=None)],
        rpa_runner=FakeRpaRunner(sample_documents[0]),
    )
    result = router.read("https://rpa.example.com/doc")
    assert result.method == RetrievalMethod.RPA
    assert result.documents[0].id == sample_documents[0].id


def test_read_falls_back_to_gui() -> None:
    router = AcquisitionRouter(
        _config(),
        api_sources=[FakeApiSource(document=None)],
        gui_reader=FakeGuiReader(text="gui body", title="GUI"),
    )
    result = router.read("https://gui.example.com/doc")
    assert result.method == RetrievalMethod.GUI
    assert result.documents[0].text


def test_allowlist_denies_unknown_host() -> None:
    router = AcquisitionRouter(_config(), api_sources=[FakeApiSource(document=None)])
    result = router.read("https://evil.example.net/doc")
    assert result.policy_verdict == "denied"
    assert result.error


def test_search_prefers_api_then_mcp(sample_documents) -> None:
    api_router = AcquisitionRouter(
        _config(),
        api_sources=[FakeApiSource(search_documents=[sample_documents[0]])],
        mcp_client=MockMcpClient(),
    )
    assert api_router.search("q").method == RetrievalMethod.API

    mcp_router = AcquisitionRouter(
        _config(),
        api_sources=[FakeApiSource(search_documents=[])],
        mcp_client=MockMcpClient(
            {
                "web_search": lambda args: [
                    {"text": "mcp result", "url": "https://mcp.example.com/result"}
                ]
            }
        ),
    )
    result = mcp_router.search("q")
    assert result.method == RetrievalMethod.MCP
    assert result.documents


def test_search_parses_arxiv_mcp_papers() -> None:
    payload = {
        "content": [
            {
                "type": "text",
                "text": (
                    '{"papers": [{"id": "2309.06180", "title": "PagedAttention", '
                    '"authors": ["Woosuk Kwon"], "abstract": "KV cache paging."}]}'
                ),
            }
        ],
        "isError": False,
    }
    router = AcquisitionRouter(
        _config(),
        api_sources=[FakeApiSource(search_documents=[])],
        mcp_client=MockMcpClient({"search_papers": lambda args: payload}),
    )
    result = router.search("PagedAttention", k=3)
    assert result.method == RetrievalMethod.MCP
    assert result.documents[0].id == "arxiv:2309.06180"
    assert result.documents[0].source_type.value == "paper"
    assert "PagedAttention" in result.documents[0].text


def test_mcp_error_payload_is_not_a_document() -> None:
    router = AcquisitionRouter(
        _config(),
        api_sources=[FakeApiSource(search_documents=[])],
        mcp_client=MockMcpClient(
            {
                "search_papers": lambda args: {
                    "content": [{"type": "text", "text": "Error: Unknown tool"}],
                    "isError": True,
                }
            }
        ),
    )
    result = router.search("q", k=1)
    assert result.documents == []
    assert result.error
