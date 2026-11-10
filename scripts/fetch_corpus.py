#!/usr/bin/env python
"""Acquire and freeze the Scout corpus (dataset method B).

Run from the repository root with the backend environment installed:

    python scripts/fetch_corpus.py --max-docs 350

Sources: arXiv API, Semantic Scholar, GitHub, HuggingFace and a small set of
official documentation pages. The script is conservative by design:

- API-first; no arbitrary URLs from model output.
- robots.txt checks for HTML documentation pages.
- rate limiting, response-size caps and idempotent writes.
- license / source metadata recorded in corpus/manifest.json.
- a frozen snapshot is written to corpus/raw/ and never re-fetched at eval time.

This script performs network I/O. It is not run automatically; the project
workflow requires explicit approval before execution.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE_BYTES = 5_000_000
USER_AGENT = "ScoutCorpusBot/0.1 (+https://github.com/; research corpus snapshot)"

ARXIV_QUERIES = [
    'all:"agent memory"',
    'all:"retrieval augmented generation"',
    'all:"LLM agent"',
    'all:"LLM recommendation"',
    'all:"inference serving"',
    'all:"KV cache"',
    'all:"tool use" AND all:LLM',
    'all:"deep research"',
]

S2_QUERIES = [
    "agent memory large language model",
    "retrieval augmented generation evaluation",
    "LLM agent tool use planning",
    "generative recommendation large language model",
    "LLM inference serving KV cache",
]

# Crossref is the reliable paper source on networks where arXiv and Semantic
# Scholar are unreachable. `has-abstract:true` keeps the corpus useful.
CROSSREF_QUERIES = [
    "agent memory large language model",
    "retrieval augmented generation evaluation",
    "LLM agent planning tool use",
    "generative recommendation large language model",
    "LLM inference serving KV cache",
    "mixture of experts inference efficiency",
    "deep research agent",
    "long context large language model",
    "agent benchmark evaluation",
    "multimodal agent",
    "RAG retrieval reranking",
    "LLM serving scheduling",
]

GITHUB_QUERIES = [
    "llm agent framework",
    "rag framework",
    "llm inference server",
    "agent memory",
    "llm recommendation",
]

HF_QUERIES = [
    "agent",
    "rag",
    "recommendation",
    "llm inference",
]

# Docs sites that are reachable directly. Others are fetched as GitHub READMEs.
DOC_URLS: list[tuple[str, str]] = [
    ("https://docs.vllm.ai/en/latest/", "vLLM documentation"),
    ("https://modelcontextprotocol.io/", "Model Context Protocol documentation"),
]

GITHUB_REPO_DOCS: list[tuple[str, str]] = [
    ("vllm-project/vllm", "vLLM README"),
    ("sgl-project/sglang", "SGLang README"),
    ("NVIDIA/TensorRT-LLM", "TensorRT-LLM README"),
    ("langchain-ai/langgraph", "LangGraph README"),
]

DEFAULT_HF_BASE = "https://hf-mirror.com"

_ROBOTS_CACHE: dict[str, RobotFileParser | None] = {}


class RateLimiter:
    def __init__(self, min_interval: float = 1.0) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delay = self.min_interval - (now - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


LIMITER = RateLimiter()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_filename(doc_id: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", doc_id).strip("_")
    name = (name or "doc")[:100]
    suffix = hashlib.sha256(doc_id.encode("utf-8")).hexdigest()[:8]
    return f"{name}_{suffix}"


def fetch(client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        LIMITER.wait()
        try:
            response = client.get(url, **kwargs)
            response.raise_for_status()
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ValueError(f"response exceeds {MAX_RESPONSE_BYTES} bytes: {url}")
            return response
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {400, 401, 403, 404}:
                raise
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def robots_allowed(client: httpx.Client, url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in _ROBOTS_CACHE:
        try:
            response = client.get(f"{base}/robots.txt", timeout=10.0)
            if response.status_code == 200:
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
                _ROBOTS_CACHE[base] = parser
            else:
                _ROBOTS_CACHE[base] = None
        except Exception:  # noqa: BLE001
            _ROBOTS_CACHE[base] = None
    parser = _ROBOTS_CACHE[base]
    return True if parser is None else parser.can_fetch("*", url)


def extract_html_text(html_text: str) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
    except ImportError:
        text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html_text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = html_lib.unescape(text)
        return re.sub(r"[ \t]+", " ", text).strip()

    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()


def write_doc(
    corpus_dir: Path,
    *,
    doc_id: str,
    title: str,
    url: str,
    source_type: str,
    trust: str,
    license_name: str | None,
    published_at: str | None,
    text: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    filename = safe_filename(doc_id) + ".md"
    relative = Path("raw") / filename
    target = corpus_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {
        "id": doc_id,
        "title": title.strip(),
        "url": url,
        "source_type": source_type,
        "trust": trust,
        "license": license_name,
        "published_at": published_at,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "content_hash": sha256_text(text),
        "path": str(relative).replace("\\", "/"),
        "metadata": metadata,
    }


def fetch_arxiv(client: httpx.Client, queries: Iterable[str], per_query: int) -> list[dict[str, Any]]:
    import xml.etree.ElementTree as ET

    namespace = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        try:
            response = fetch(
                client,
                "https://export.arxiv.org/api/query",
                params={"search_query": query, "start": 0, "max_results": per_query},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[arxiv] query failed: {query}: {exc}", file=sys.stderr)
            continue
        root = ET.fromstring(response.text)
        for node in root.findall("a:entry", namespace):
            raw_id = node.findtext("a:id", default="", namespaces=namespace)
            arxiv_id = raw_id.rsplit("/abs/", 1)[-1].strip()
            if not arxiv_id or arxiv_id in seen:
                continue
            seen.add(arxiv_id)
            title = " ".join(node.findtext("a:title", default="", namespaces=namespace).split())
            summary = " ".join(node.findtext("a:summary", default="", namespaces=namespace).split())
            published = node.findtext("a:published", default=None, namespaces=namespace)
            authors = [
                author.findtext("a:name", default="", namespaces=namespace)
                for author in node.findall("a:author", namespace)
            ]
            categories = [item.get("term", "") for item in node.findall("a:category", namespace)]
            text = (
                f"# {title}\n\n"
                f"Source: {raw_id}\n\n"
                f"## Abstract\n\n{summary}\n\n"
                f"## Authors\n\n{', '.join(authors)}\n\n"
                f"## Categories\n\n{', '.join(categories)}\n"
            )
            entries.append(
                {
                    "id": f"arxiv:{arxiv_id}",
                    "title": title,
                    "url": raw_id,
                    "source_type": "paper",
                    "trust": "primary",
                    "license": "arXiv (see paper)",
                    "published_at": published,
                    "text": text,
                    "metadata": {"authors": authors, "categories": categories},
                }
            )
    return entries


def fetch_semantic_scholar(
    client: httpx.Client, queries: Iterable[str], per_query: int
) -> list[dict[str, Any]]:
    fields = "title,abstract,url,year,authors,venue,externalIds,openAccessPdf,license"
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        try:
            response = fetch(
                client,
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": query, "limit": per_query, "fields": fields},
            )
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[s2] query failed: {query}: {exc}", file=sys.stderr)
            continue
        for paper in payload.get("data", []):
            paper_id = paper.get("paperId")
            if not paper_id or paper_id in seen:
                continue
            seen.add(paper_id)
            title = paper.get("title") or "Untitled"
            abstract = paper.get("abstract") or ""
            authors = [author.get("name", "") for author in (paper.get("authors") or [])]
            venue = paper.get("venue") or ""
            text = (
                f"# {title}\n\n"
                f"Source: https://www.semanticscholar.org/paper/{paper_id}\n\n"
                f"## Abstract\n\n{abstract}\n\n"
                f"## Authors\n\n{', '.join(authors)}\n\n"
                f"## Venue\n\n{venue}\n\n"
                f"## Year\n\n{paper.get('year') or ''}\n"
            )
            entries.append(
                {
                    "id": f"s2:{paper_id}",
                    "title": title,
                    "url": paper.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
                    "source_type": "paper",
                    "trust": "primary",
                    "license": paper.get("license") or "unknown",
                    "published_at": str(paper.get("year") or ""),
                    "text": text,
                    "metadata": {
                        "authors": authors,
                        "venue": venue,
                        "external_ids": paper.get("externalIds") or {},
                    },
                }
            )
    return entries


def strip_jats(text: str) -> str:
    text = re.sub(r"(?s)<[^>]+>", " ", text or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_crossref(
    client: httpx.Client,
    queries: Iterable[str],
    per_query: int,
    *,
    mailto: str | None,
) -> list[dict[str, Any]]:
    select = (
        "DOI,title,abstract,author,published,URL,container-title,type,"
        "license,is-referenced-by-count"
    )
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        params: dict[str, Any] = {
            "query": query,
            "rows": per_query,
            "filter": "has-abstract:true",
            "select": select,
        }
        if mailto:
            params["mailto"] = mailto
        try:
            response = fetch(client, "https://api.crossref.org/works", params=params)
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[crossref] query failed: {query}: {exc}", file=sys.stderr)
            continue
        for item in payload.get("message", {}).get("items", []):
            doi = item.get("DOI")
            if not doi or doi in seen:
                continue
            seen.add(doi)
            titles = item.get("title") or []
            title = titles[0] if titles else "Untitled"
            abstract = strip_jats(item.get("abstract") or "")
            if not abstract:
                continue
            authors = [
                " ".join(part for part in (a.get("given"), a.get("family")) if part)
                for a in (item.get("author") or [])
            ]
            venues = item.get("container-title") or []
            venue = venues[0] if venues else ""
            published_parts = (item.get("published") or {}).get("date-parts") or [[None]]
            year = published_parts[0][0] if published_parts and published_parts[0] else None
            licenses = item.get("license") or []
            license_name = licenses[0].get("URL") if licenses else "unknown"
            text = (
                f"# {title}\n\n"
                f"Source: {item.get('URL') or 'https://doi.org/' + doi}\n\n"
                f"## Abstract\n\n{abstract}\n\n"
                f"## Authors\n\n{', '.join(authors)}\n\n"
                f"## Venue\n\n{venue}\n\n"
                f"## Year\n\n{year or ''}\n\n"
                f"## DOI\n\n{doi}\n"
            )
            entries.append(
                {
                    "id": f"crossref:{doi}",
                    "title": title,
                    "url": item.get("URL") or f"https://doi.org/{doi}",
                    "source_type": "paper",
                    "trust": "primary",
                    "license": license_name,
                    "published_at": str(year) if year else None,
                    "text": text,
                    "metadata": {
                        "authors": authors,
                        "venue": venue,
                        "doi": doi,
                        "type": item.get("type"),
                        "citations": item.get("is-referenced-by-count", 0),
                    },
                }
            )
    return entries


def fetch_github(
    client: httpx.Client,
    queries: Iterable[str],
    per_query: int,
    *,
    with_readmes: bool,
    token: str | None,
    max_readmes: int = 20,
) -> list[dict[str, Any]]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    readmes_fetched = 0
    for query in queries:
        try:
            response = fetch(
                client,
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": per_query},
                headers=headers,
            )
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[github] query failed: {query}: {exc}", file=sys.stderr)
            continue
        for repo in payload.get("items", []):
            full_name = repo.get("full_name")
            if not full_name or full_name in seen:
                continue
            seen.add(full_name)
            license_name = (repo.get("license") or {}).get("spdx_id") or "unknown"
            readme = ""
            if with_readmes and readmes_fetched < max_readmes:
                try:
                    readme_response = fetch(
                        client,
                        f"https://api.github.com/repos/{full_name}/readme",
                        headers={**headers, "Accept": "application/vnd.github.raw"},
                    )
                    readme = readme_response.text
                    readmes_fetched += 1
                except Exception:  # noqa: BLE001
                    readme = ""
            description = repo.get("description") or ""
            topics = repo.get("topics") or []
            text = (
                f"# {full_name}\n\n"
                f"Source: {repo.get('html_url', '')}\n\n"
                f"## Description\n\n{description}\n\n"
                f"## Topics\n\n{', '.join(topics)}\n\n"
                f"## Stars\n\n{repo.get('stargazers_count', 0)}\n\n"
                f"## License\n\n{license_name}\n\n"
                f"## README\n\n{readme}\n"
            )
            entries.append(
                {
                    "id": f"github:{full_name}",
                    "title": full_name,
                    "url": repo.get("html_url", ""),
                    "source_type": "code_repo",
                    "trust": "primary" if license_name != "unknown" else "secondary",
                    "license": license_name,
                    "published_at": None,
                    "text": text,
                    "metadata": {
                        "stars": repo.get("stargazers_count", 0),
                        "topics": topics,
                        "language": repo.get("language"),
                    },
                }
            )
    return entries


def fetch_huggingface(
    client: httpx.Client,
    queries: Iterable[str],
    per_query: int,
    *,
    with_readmes: bool,
    base_url: str = DEFAULT_HF_BASE,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        try:
            response = fetch(
                client,
                f"{base_url.rstrip('/')}/api/models",
                params={"search": query, "limit": per_query, "full": "true"},
            )
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[hf] query failed: {query}: {exc}", file=sys.stderr)
            continue
        if not isinstance(payload, list):
            print(f"[hf] unexpected payload for: {query}", file=sys.stderr)
            continue
        for model in payload:
            model_id = model.get("id")
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            card = model.get("cardData") or {}
            license_name = card.get("license") or "unknown"
            readme = ""
            if with_readmes:
                try:
                    readme_response = fetch(
                        client,
                        f"{base_url.rstrip('/')}/{model_id}/raw/main/README.md",
                    )
                    readme = readme_response.text
                except Exception:  # noqa: BLE001
                    readme = ""
            tags = model.get("tags") or []
            text = (
                f"# {model_id}\n\n"
                f"Source: https://huggingface.co/{model_id}\n\n"
                f"## Pipeline\n\n{model.get('pipeline_tag') or ''}\n\n"
                f"## Tags\n\n{', '.join(tags)}\n\n"
                f"## Downloads\n\n{model.get('downloads', 0)}\n\n"
                f"## Likes\n\n{model.get('likes', 0)}\n\n"
                f"## Model Card\n\n{readme}\n"
            )
            entries.append(
                {
                    "id": f"hf:{model_id}",
                    "title": model_id,
                    "url": f"https://huggingface.co/{model_id}",
                    "source_type": "model_card",
                    "trust": "primary",
                    "license": license_name,
                    "published_at": None,
                    "text": text,
                    "metadata": {
                        "pipeline_tag": model.get("pipeline_tag"),
                        "tags": tags,
                        "downloads": model.get("downloads", 0),
                    },
                }
            )
    return entries


def fetch_docs(client: httpx.Client, documents: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for url, title in documents:
        if not robots_allowed(client, url):
            print(f"[docs] robots.txt disallows: {url}", file=sys.stderr)
            continue
        try:
            response = fetch(client, url)
            text = extract_html_text(response.text)
        except Exception as exc:  # noqa: BLE001
            print(f"[docs] fetch failed: {url}: {exc}", file=sys.stderr)
            continue
        parsed = urlparse(url)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", parsed.path).strip("-") or "index"
        doc_id = f"docs:{parsed.netloc}:{slug}"
        entries.append(
            {
                "id": doc_id,
                "title": title,
                "url": url,
                "source_type": "official_doc",
                "trust": "primary",
                "license": "site terms",
                "published_at": None,
                "text": f"# {title}\n\nSource: {url}\n\n{text}\n",
                "metadata": {"host": parsed.netloc},
            }
        )
    return entries


def fetch_repo_docs(
    client: httpx.Client,
    repos: Iterable[tuple[str, str]],
    *,
    token: str | None,
) -> list[dict[str, Any]]:
    headers = {"Accept": "application/vnd.github.raw"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    entries: list[dict[str, Any]] = []
    for repo, title in repos:
        try:
            response = fetch(client, f"https://api.github.com/repos/{repo}/readme", headers=headers)
        except Exception as exc:  # noqa: BLE001
            print(f"[repo-docs] fetch failed: {repo}: {exc}", file=sys.stderr)
            continue
        text = response.text.strip()
        if not text:
            continue
        entries.append(
            {
                "id": f"docs:github:{repo}",
                "title": title,
                "url": f"https://github.com/{repo}",
                "source_type": "official_doc",
                "trust": "primary",
                "license": "repo license",
                "published_at": None,
                "text": f"# {title}\n\nSource: https://github.com/{repo}\n\n{text}\n",
                "metadata": {"repo": repo},
            }
        )
    return entries


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "generated_at": None, "documents": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def add_entries(
    manifest: dict[str, Any],
    existing: set[str],
    entries: Iterable[dict[str, Any]],
    corpus_dir: Path,
    max_docs: int,
) -> int:
    added = 0
    for entry in entries:
        if len(manifest["documents"]) >= max_docs:
            break
        if entry["id"] in existing:
            continue
        written = write_doc(
            corpus_dir,
            doc_id=entry["id"],
            title=entry["title"],
            url=entry["url"],
            source_type=entry["source_type"],
            trust=entry["trust"],
            license_name=entry.get("license"),
            published_at=entry.get("published_at"),
            text=entry["text"],
            metadata=entry.get("metadata") or {},
        )
        if written is None:
            continue
        manifest["documents"].append(written)
        existing.add(written["id"])
        added += 1
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch and freeze the Scout corpus")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "corpus"))
    parser.add_argument("--max-docs", type=int, default=350)
    parser.add_argument("--per-query", type=int, default=20)
    parser.add_argument(
        "--only",
        default="crossref,github,hf,docs",
        help="comma-separated sources: crossref,arxiv,s2,github,hf,docs",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--with-readmes", action="store_true", help="fetch GitHub/HF READMEs")
    parser.add_argument("--max-readmes", type=int, default=20)
    parser.add_argument("--crossref-mailto", default=None)
    parser.add_argument("--hf-base", default=DEFAULT_HF_BASE)
    parser.add_argument("--s2-key", default=None)
    parser.add_argument("--github-token", default=None)
    args = parser.parse_args(argv)

    sources = {item.strip() for item in args.only.split(",") if item.strip()}
    if args.dry_run:
        print(
            json.dumps(
                {
                    "crossref_queries": CROSSREF_QUERIES,
                    "arxiv_queries": ARXIV_QUERIES,
                    "s2_queries": S2_QUERIES,
                    "github_queries": GITHUB_QUERIES,
                    "hf_queries": HF_QUERIES,
                    "hf_base": args.hf_base,
                    "docs": [url for url, _ in DOC_URLS],
                    "repo_docs": [repo for repo, _ in GITHUB_REPO_DOCS],
                    "max_docs": args.max_docs,
                    "per_query": args.per_query,
                    "sources": sorted(sources),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    corpus_dir = Path(args.out)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = corpus_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    existing = {entry["id"] for entry in manifest.get("documents", [])}

    headers = {"User-Agent": USER_AGENT}
    if args.s2_key:
        headers["x-api-key"] = args.s2_key
    # trust_env=False is deliberate: the Windows registry proxy is broken for
    # TLS in this environment, while direct access works for the sources below.
    with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers, trust_env=False) as client:
        if "crossref" in sources:
            added = add_entries(
                manifest,
                existing,
                fetch_crossref(
                    client,
                    CROSSREF_QUERIES,
                    args.per_query,
                    mailto=args.crossref_mailto,
                ),
                corpus_dir,
                args.max_docs,
            )
            print(f"[crossref] added {added}", file=sys.stderr)
            save_manifest(manifest_path, manifest)

        if "arxiv" in sources and len(manifest["documents"]) < args.max_docs:
            added = add_entries(
                manifest,
                existing,
                fetch_arxiv(client, ARXIV_QUERIES, args.per_query),
                corpus_dir,
                args.max_docs,
            )
            print(f"[arxiv] added {added}", file=sys.stderr)
            save_manifest(manifest_path, manifest)

        if "s2" in sources and len(manifest["documents"]) < args.max_docs:
            added = add_entries(
                manifest,
                existing,
                fetch_semantic_scholar(client, S2_QUERIES, args.per_query),
                corpus_dir,
                args.max_docs,
            )
            print(f"[s2] added {added}", file=sys.stderr)
            save_manifest(manifest_path, manifest)

        if "github" in sources and len(manifest["documents"]) < args.max_docs:
            added = add_entries(
                manifest,
                existing,
                fetch_github(
                    client,
                    GITHUB_QUERIES,
                    args.per_query,
                    with_readmes=args.with_readmes,
                    token=args.github_token,
                    max_readmes=args.max_readmes,
                ),
                corpus_dir,
                args.max_docs,
            )
            print(f"[github] added {added}", file=sys.stderr)
            save_manifest(manifest_path, manifest)

        if "hf" in sources and len(manifest["documents"]) < args.max_docs:
            added = add_entries(
                manifest,
                existing,
                fetch_huggingface(
                    client,
                    HF_QUERIES,
                    args.per_query,
                    with_readmes=args.with_readmes,
                    base_url=args.hf_base,
                ),
                corpus_dir,
                args.max_docs,
            )
            print(f"[hf] added {added}", file=sys.stderr)
            save_manifest(manifest_path, manifest)

        if "docs" in sources and len(manifest["documents"]) < args.max_docs:
            doc_entries = fetch_docs(client, DOC_URLS)
            doc_entries.extend(
                fetch_repo_docs(client, GITHUB_REPO_DOCS, token=args.github_token)
            )
            added = add_entries(
                manifest,
                existing,
                doc_entries,
                corpus_dir,
                args.max_docs,
            )
            print(f"[docs] added {added}", file=sys.stderr)
            save_manifest(manifest_path, manifest)

    manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_manifest(manifest_path, manifest)
    print(
        json.dumps(
            {
                "ok": True,
                "manifest": str(manifest_path),
                "documents": len(manifest["documents"]),
                "raw_dir": str(corpus_dir / "raw"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
