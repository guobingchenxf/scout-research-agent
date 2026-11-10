"""Programmatic sources used by the acquisition router.

All adapters are read-only and return a normalized `SourceDocument`. They use
`trust_env=False` for the same reason as the corpus script: the Windows
registry proxy is broken for TLS in this environment, while direct access to
Crossref/GitHub/HF mirror/docs works.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import re
from typing import Any, ClassVar, Protocol
from urllib.parse import urlparse

import httpx

from ..config import ScoutConfig
from ..models import (
    RetrievalMethod,
    SourceDocument,
    SourceType,
    TrustLevel,
    utc_now,
)

USER_AGENT = "ScoutAgent/0.1 (research; read-only)"


class ApiSourceError(Exception):
    pass


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_jats(text: str) -> str:
    text = re.sub(r"(?s)<[^>]+>", " ", text or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


class ApiSource(Protocol):
    name: str

    def supports(self, url: str) -> bool: ...

    def search(self, query: str, k: int) -> list[SourceDocument]: ...

    def read(self, url: str) -> SourceDocument | None: ...


class HttpApiSource:
    name = "http"

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            trust_env=False,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        self._client.close()

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self._client.get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        response = self._client.get(url, **kwargs)
        response.raise_for_status()
        return response.text


class CrossrefApiSource(HttpApiSource):
    name = "crossref"

    def supports(self, url: str) -> bool:
        return urlparse(url).netloc.lower() in {"api.crossref.org", "doi.org", "dx.doi.org"}

    def search(self, query: str, k: int) -> list[SourceDocument]:
        payload = self.get_json(
            "https://api.crossref.org/works",
            params={
                "query": query,
                "rows": k,
                "filter": "has-abstract:true",
                "select": (
                    "DOI,title,abstract,author,published,URL,container-title,type,"
                    "license,is-referenced-by-count"
                ),
            },
        )
        return [
            self._document(item)
            for item in payload.get("message", {}).get("items", [])
            if item.get("DOI")
        ]

    def read(self, url: str) -> SourceDocument | None:
        parsed = urlparse(url)
        doi = parsed.path.lstrip("/")
        if parsed.netloc.lower().startswith("api.crossref.org"):
            doi = doi.split("/works/", 1)[-1]
        if not doi:
            return None
        payload = self.get_json(f"https://api.crossref.org/works/{doi}")
        item = payload.get("message")
        return self._document(item) if isinstance(item, dict) else None

    def _document(self, item: dict[str, Any]) -> SourceDocument:
        doi = item.get("DOI") or ""
        titles = item.get("title") or []
        title = titles[0] if titles else "Untitled"
        abstract = strip_jats(item.get("abstract") or "")
        authors = [
            " ".join(part for part in (a.get("given"), a.get("family")) if part)
            for a in (item.get("author") or [])
        ]
        venues = item.get("container-title") or []
        venue = venues[0] if venues else ""
        date_parts = (item.get("published") or {}).get("date-parts") or [[None]]
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        licenses = item.get("license") or []
        license_name = licenses[0].get("URL") if licenses else "unknown"
        text = (
            f"# {title}\n\nSource: {item.get('URL') or 'https://doi.org/' + doi}\n\n"
            f"## Abstract\n\n{abstract}\n\n## Authors\n\n{', '.join(authors)}\n\n"
            f"## Venue\n\n{venue}\n\n## Year\n\n{year or ''}\n\n## DOI\n\n{doi}\n"
        )
        return SourceDocument(
            id=f"crossref:{doi}",
            title=title,
            url=item.get("URL") or f"https://doi.org/{doi}",
            source_type=SourceType.PAPER,
            trust=TrustLevel.PRIMARY,
            retrieval_method=RetrievalMethod.API,
            license=license_name,
            published_at=str(year) if year else None,
            fetched_at=utc_now(),
            content_hash=_hash(text),
            text=text,
            metadata={
                "authors": authors,
                "venue": venue,
                "doi": doi,
                "type": item.get("type"),
                "citations": item.get("is-referenced-by-count", 0),
            },
        )


class GitHubApiSource(HttpApiSource):
    name = "github"

    def __init__(self, token: str | None = None, *, timeout: float = 30.0) -> None:
        super().__init__(timeout=timeout)
        self.token = token

    def supports(self, url: str) -> bool:
        return urlparse(url).netloc.lower() in {"github.com", "api.github.com"}

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {"Accept": accept}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def search(self, query: str, k: int) -> list[SourceDocument]:
        payload = self.get_json(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": k},
            headers=self._headers(),
        )
        return [
            self._document(item)
            for item in payload.get("items", [])
            if item.get("full_name")
        ]

    def read(self, url: str) -> SourceDocument | None:
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc.lower() == "api.github.com" and len(parts) >= 2:
            repo = f"{parts[1]}/{parts[2]}" if parts[0] == "repos" else ""
        else:
            repo = "/".join(parts[:2])
        if not repo:
            return None
        text = self.get_text(
            f"https://api.github.com/repos/{repo}/readme",
            headers=self._headers("application/vnd.github.raw"),
        )
        title = f"{repo} README"
        content = f"# {title}\n\nSource: https://github.com/{repo}\n\n{text}\n"
        return SourceDocument(
            id=f"docs:github:{repo}",
            title=title,
            url=f"https://github.com/{repo}",
            source_type=SourceType.OFFICIAL_DOC,
            trust=TrustLevel.PRIMARY,
            retrieval_method=RetrievalMethod.API,
            license="repo license",
            fetched_at=utc_now(),
            content_hash=_hash(content),
            text=content,
            metadata={"repo": repo},
        )

    def _document(self, item: dict[str, Any]) -> SourceDocument:
        full_name = item.get("full_name", "")
        license_name = (item.get("license") or {}).get("spdx_id") or "unknown"
        topics = item.get("topics") or []
        text = (
            f"# {full_name}\n\nSource: {item.get('html_url', '')}\n\n"
            f"## Description\n\n{item.get('description') or ''}\n\n"
            f"## Topics\n\n{', '.join(topics)}\n\n"
            f"## Stars\n\n{item.get('stargazers_count', 0)}\n\n"
            f"## License\n\n{license_name}\n"
        )
        return SourceDocument(
            id=f"github:{full_name}",
            title=full_name,
            url=item.get("html_url", ""),
            source_type=SourceType.CODE_REPO,
            trust=TrustLevel.PRIMARY if license_name != "unknown" else TrustLevel.SECONDARY,
            retrieval_method=RetrievalMethod.API,
            license=license_name,
            fetched_at=utc_now(),
            content_hash=_hash(text),
            text=text,
            metadata={
                "stars": item.get("stargazers_count", 0),
                "topics": topics,
                "language": item.get("language"),
            },
        )


class HuggingFaceMirrorSource(HttpApiSource):
    name = "hf-mirror"

    def __init__(self, base_url: str = "https://hf-mirror.com", *, timeout: float = 30.0) -> None:
        super().__init__(timeout=timeout)
        self.base_url = base_url.rstrip("/")

    def supports(self, url: str) -> bool:
        return urlparse(url).netloc.lower() in {"hf-mirror.com", "huggingface.co"}

    def search(self, query: str, k: int) -> list[SourceDocument]:
        payload = self.get_json(
            f"{self.base_url}/api/models",
            params={"search": query, "limit": k, "full": "true"},
        )
        if not isinstance(payload, list):
            return []
        return [self._document(item) for item in payload if item.get("id")]

    def read(self, url: str) -> SourceDocument | None:
        parsed = urlparse(url)
        model_id = parsed.path.strip("/")
        if not model_id:
            return None
        text = self.get_text(f"{self.base_url}/{model_id}/raw/main/README.md")
        content = f"# {model_id}\n\nSource: https://huggingface.co/{model_id}\n\n{text}\n"
        return SourceDocument(
            id=f"hf:{model_id}",
            title=model_id,
            url=f"https://huggingface.co/{model_id}",
            source_type=SourceType.MODEL_CARD,
            trust=TrustLevel.PRIMARY,
            retrieval_method=RetrievalMethod.API,
            license="model card license",
            fetched_at=utc_now(),
            content_hash=_hash(content),
            text=content,
            metadata={"model_id": model_id},
        )

    def _document(self, item: dict[str, Any]) -> SourceDocument:
        model_id = item.get("id", "")
        card = item.get("cardData") or {}
        license_name = card.get("license") or "unknown"
        tags = item.get("tags") or []
        text = (
            f"# {model_id}\n\nSource: https://huggingface.co/{model_id}\n\n"
            f"## Pipeline\n\n{item.get('pipeline_tag') or ''}\n\n"
            f"## Tags\n\n{', '.join(tags)}\n\n"
            f"## Downloads\n\n{item.get('downloads', 0)}\n"
        )
        return SourceDocument(
            id=f"hf:{model_id}",
            title=model_id,
            url=f"https://huggingface.co/{model_id}",
            source_type=SourceType.MODEL_CARD,
            trust=TrustLevel.PRIMARY,
            retrieval_method=RetrievalMethod.API,
            license=license_name,
            fetched_at=utc_now(),
            content_hash=_hash(text),
            text=text,
            metadata={"pipeline_tag": item.get("pipeline_tag"), "tags": tags},
        )


class DocsApiSource(HttpApiSource):
    name = "docs"

    ALLOWED_HOSTS: ClassVar[set[str]] = {
        "docs.vllm.ai",
        "docs.sglang.ai",
        "nvidia.github.io",
        "langchain-ai.github.io",
        "modelcontextprotocol.io",
    }

    def supports(self, url: str) -> bool:
        return urlparse(url).netloc.lower() in self.ALLOWED_HOSTS

    def search(self, query: str, k: int) -> list[SourceDocument]:
        return []

    def read(self, url: str) -> SourceDocument | None:
        parsed = urlparse(url)
        text = strip_html(self.get_text(url))
        slug = re.sub(r"[^A-Za-z0-9]+", "-", parsed.path).strip("-") or "index"
        title = f"{parsed.netloc} {slug}"
        content = f"# {title}\n\nSource: {url}\n\n{text}\n"
        return SourceDocument(
            id=f"docs:{parsed.netloc}:{slug}",
            title=title,
            url=url,
            source_type=SourceType.OFFICIAL_DOC,
            trust=TrustLevel.PRIMARY,
            retrieval_method=RetrievalMethod.API,
            license="site terms",
            fetched_at=utc_now(),
            content_hash=_hash(content),
            text=content,
            metadata={"host": parsed.netloc},
        )


def default_api_sources(config: ScoutConfig) -> list[ApiSource]:
    return [
        CrossrefApiSource(),
        GitHubApiSource(),
        HuggingFaceMirrorSource(),
        DocsApiSource(),
    ]
