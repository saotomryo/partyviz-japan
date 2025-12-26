from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
import base64
import json
import posixpath
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, unquote, urljoin, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.debug import ensure_run_dir, save_json
from ..agents.fetchers import HttpxFetcher
from ..agents.text_extract import html_to_text
from ..db import models
from ..settings import settings
from .policy_sources import list_sources


@dataclass
class CrawlStats:
    fetched_html: int = 0
    fetched_pdf: int = 0
    skipped: int = 0
    errors: int = 0


class _LinkExtractor:
    def __init__(self) -> None:
        self.links: list[str] = []

    def feed(self, html: str) -> None:
        for m in re.finditer(r'href=[\"\\\']([^\"\\\']+)', html or "", flags=re.IGNORECASE):
            self.links.append(m.group(1))


def _markdown_links(text: str) -> list[str]:
    links: list[str] = []
    for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text or ""):
        links.append(m.group(1))
    for m in re.finditer(r"(https?://[^\s)]+)", text or ""):
        links.append(m.group(1))
    return links


def _markdown_to_text(text: str) -> str:
    t = re.sub(r"```.*?```", "", text or "", flags=re.DOTALL)
    t = re.sub(r"`[^`]+`", "", t)
    t = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", t)
    t = re.sub(r"#+\s*", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

def _policy_view_repo_path(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.netloc.lower() != "policy.team-mir.ai":
        return None
    if not parsed.path.startswith("/view/"):
        return None
    path = parsed.path[len("/view/") :]
    path = path.strip("/")
    if not path:
        return ""
    return unquote(path)


def _policy_view_url_for_path(repo_path: str) -> str:
    path = repo_path.strip("/")
    encoded = quote(path)
    return f"https://policy.team-mir.ai/view/{encoded}"


def _policy_view_resolve_link(base_repo_path: str, link: str) -> str:
    if link.startswith("http://") or link.startswith("https://"):
        return link
    if link.startswith("#"):
        return ""
    base_dir = posixpath.dirname(base_repo_path or "")
    joined = posixpath.normpath(posixpath.join(base_dir, link))
    return _policy_view_url_for_path(joined)


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("#"):
        return ""
    return u.split("#", 1)[0]


def _same_domain(url: str, domain: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    dom = domain.lower()
    if host == dom:
        return True
    if host == "www." + dom:
        return True
    if dom.startswith("www.") and host == dom.removeprefix("www."):
        return True
    return False


def _path_allowed(url: str, base_path: str) -> bool:
    try:
        path = urlparse(url).path or "/"
    except Exception:
        return False
    if base_path == "/":
        return True
    if not base_path.endswith("/"):
        base_path = base_path + "/"
    return path.startswith(base_path)


def _base_path_from_url(url: str) -> str:
    path = urlparse(url).path or "/"
    if path == "/":
        return "/"
    if not path.endswith("/"):
        path = path + "/"
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "/"
    last = parts[-1]
    if "." in last:
        return "/" + "/".join(parts[:-1]) + "/"
    return path


def _hash_text(text: str) -> str:
    h = hashlib.sha256()
    h.update((text or "").encode("utf-8"))
    return h.hexdigest()

def _hash_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data or b"")
    return h.hexdigest()


def _chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    t = " ".join((text or "").split())
    if not t:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(t):
        end = min(len(t), start + chunk_size)
        chunks.append(t[start:end])
        if end == len(t):
            break
        start = max(0, end - overlap)
    return chunks


def _extract_pdf_text(data: bytes) -> tuple[str, str | None]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        PdfReader = None  # type: ignore[assignment]
    try:
        from pdfminer.high_level import extract_text  # type: ignore
    except Exception:
        extract_text = None  # type: ignore[assignment]

    if PdfReader is None and extract_text is None:
        return "", "extractor_missing"

    if PdfReader is not None:
        try:
            reader = PdfReader(data)
        except Exception as e:
            reader = None
            last_err = f"pypdf:{type(e).__name__}"
        if reader is not None:
            parts: list[str] = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    continue
            text = "\n".join([p for p in parts if p]).strip()
            if text:
                return text, None

    if extract_text is not None:
        try:
            text = extract_text(data) or ""
        except Exception as e:
            text = ""
            last_err = f"pdfminer:{type(e).__name__}"
        if text.strip():
            return text.strip(), None

    return "", f"extract_failed:{locals().get('last_err', 'unknown')}"
    try:
        reader = PdfReader(data)
    except Exception:
        return ""
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join([p for p in parts if p]).strip()


def _upsert_document(
    db: Session,
    *,
    party_id,
    url: str,
    doc_type: str,
    content_text: str,
    title: str | None = None,
) -> models.PolicyDocument:
    content_hash = _hash_text(content_text)
    doc = db.scalar(select(models.PolicyDocument).where(models.PolicyDocument.url == url))
    if doc and doc.hash == content_hash:
        return doc
    if not doc:
        doc = models.PolicyDocument(party_id=party_id, url=url, doc_type=doc_type)
        db.add(doc)
    doc.title = title
    doc.content_text = content_text
    doc.hash = content_hash
    db.flush()
    return doc


def _replace_chunks(db: Session, *, doc: models.PolicyDocument, party_id, chunks: Iterable[str]) -> None:
    db.query(models.PolicyChunk).filter(models.PolicyChunk.doc_id == doc.doc_id).delete()
    for idx, text in enumerate(chunks):
        db.add(
            models.PolicyChunk(
                doc_id=doc.doc_id,
                party_id=party_id,
                chunk_index=idx,
                content=text,
                embedding=None,
                meta={"source_url": doc.url, "title": doc.title},
            )
        )


def crawl_party_policy_sources(
    db: Session,
    *,
    party_id,
    max_urls: int = 200,
    max_depth: int = 2,
) -> CrawlStats:
    sources = list_sources(db, party_id)
    if not sources:
        raise ValueError("policy sources not found")

    party = db.get(models.PartyRegistry, party_id)
    if not party:
        raise ValueError("party not found")

    fetcher = HttpxFetcher(timeout=30)
    stats = CrawlStats()
    visited: set[str] = set()
    queue: list[tuple[str, str, str, int]] = []
    for s in sources:
        base_url = _normalize_url(s.base_url)
        if not base_url:
            continue
        pu = urlparse(base_url)
        base_path = _base_path_from_url(base_url)
        queue.append((base_url, pu.netloc, base_path, max_depth))

    log: dict[str, list[dict]] = {"fetched": [], "skipped": [], "errors": []}
    run_dir = None
    if settings.agent_save_runs:
        run_dir = ensure_run_dir(Path(__file__).resolve().parents[2] / "runs" / "policy_crawl")
    while queue and len(visited) < max_urls:
        url, domain, base_path, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        repo_path = _policy_view_repo_path(url)
        if repo_path is not None:
            api_url = f"https://api.github.com/repos/team-mirai/policy/contents/{quote(repo_path)}"
            try:
                resp = fetcher.client.get(api_url, headers={"Accept": "application/vnd.github.v3+json"})
            except Exception as e:
                stats.errors += 1
                log["errors"].append({"url": url, "reason": "github_api_error", "detail": str(e)})
                continue

            status = int(getattr(resp, "status_code", 0) or 0)
            if status < 200 or status >= 400:
                stats.skipped += 1
                log["skipped"].append({"url": url, "reason": f"github_api_http_{status}"})
                continue
            try:
                payload = resp.json()
            except Exception:
                stats.skipped += 1
                log["skipped"].append({"url": url, "reason": "github_api_invalid_json"})
                continue

            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    path = item.get("path")
                    item_type = item.get("type")
                    if not path or item_type not in {"file", "dir"}:
                        continue
                    next_url = _policy_view_url_for_path(path)
                    if next_url not in visited:
                        queue.append((next_url, domain, base_path, depth - 1))
                stats.fetched_html += 1
                log["fetched"].append({"url": url, "type": "github_dir", "status": status})
                continue

            if isinstance(payload, dict) and payload.get("type") == "file":
                content = payload.get("content")
                encoding = payload.get("encoding")
                name = payload.get("name") or repo_path
                if content and encoding == "base64":
                    try:
                        raw = base64.b64decode(content)
                    except Exception:
                        raw = b""
                    text = raw.decode("utf-8", errors="ignore")
                else:
                    text = ""
                if not text:
                    stats.skipped += 1
                    log["skipped"].append({"url": url, "reason": "github_file_empty"})
                    continue
                text_clean = _markdown_to_text(text)
                if not text_clean:
                    stats.skipped += 1
                    log["skipped"].append({"url": url, "reason": "github_file_text_empty"})
                    continue
                doc = _upsert_document(db, party_id=party_id, url=url, doc_type="markdown", content_text=text_clean, title=str(name))
                _replace_chunks(db, doc=doc, party_id=party_id, chunks=_chunk_text(text_clean))
                stats.fetched_html += 1
                log["fetched"].append({"url": url, "type": "markdown", "status": status})
                for raw_link in _markdown_links(text):
                    next_url = _policy_view_resolve_link(repo_path, raw_link)
                    if next_url and next_url not in visited:
                        queue.append((next_url, domain, base_path, depth - 1))
                continue

        try:
            resp = fetcher.client.get(url, timeout=fetcher.client.timeout)
        except Exception as e:
            stats.errors += 1
            log["errors"].append({"url": url, "reason": "fetch_error", "detail": str(e)})
            continue

        status = int(getattr(resp, "status_code", 0) or 0)
        if status < 200 or status >= 400:
            stats.skipped += 1
            log["skipped"].append({"url": url, "reason": f"http_{status}"})
            continue

        content_type = (resp.headers.get("content-type") or "").lower()
        body = resp.content or b""
        if url.lower().endswith(".pdf") or "application/pdf" in content_type:
            text, err = _extract_pdf_text(body)
            if not text:
                saved_path = None
                if run_dir is not None:
                    digest = _hash_bytes(body)[:12]
                    saved_path = str(run_dir / f"pdf_failed_{digest}.pdf")
                    try:
                        Path(saved_path).write_bytes(body)
                    except Exception:
                        saved_path = None
                stats.skipped += 1
                entry = {"url": url, "reason": err or "pdf_text_empty"}
                if saved_path:
                    entry["saved_path"] = saved_path
                log["skipped"].append(entry)
                continue
            doc = _upsert_document(db, party_id=party_id, url=url, doc_type="pdf", content_text=text, title=None)
            _replace_chunks(db, doc=doc, party_id=party_id, chunks=_chunk_text(text))
            stats.fetched_pdf += 1
            log["fetched"].append({"url": url, "type": "pdf", "status": status})
            continue

        is_markdown = "text/markdown" in content_type or url.lower().endswith(".md") or url.lower().endswith(".md/")
        is_text = "text/plain" in content_type
        if (not is_markdown) and (not is_text) and "text/html" not in content_type and not url.endswith("/"):
            stats.skipped += 1
            log["skipped"].append({"url": url, "reason": "non_html"})
            continue
        html = body.decode(resp.encoding or "utf-8", errors="ignore")
        text = _markdown_to_text(html) if is_markdown else html_to_text(html)
        if not text:
            stats.skipped += 1
            log["skipped"].append({"url": url, "reason": "html_text_empty"})
        else:
            doc_type = "markdown" if is_markdown else ("text" if is_text else "html")
            doc = _upsert_document(db, party_id=party_id, url=url, doc_type=doc_type, content_text=text, title=None)
            _replace_chunks(db, doc=doc, party_id=party_id, chunks=_chunk_text(text))
            stats.fetched_html += 1
            log["fetched"].append({"url": url, "type": doc_type, "status": status})

        if depth <= 0:
            continue
        link_candidates: list[str] = []
        if is_markdown:
            link_candidates.extend(_markdown_links(html))
        else:
            extractor = _LinkExtractor()
            extractor.feed(html)
            link_candidates.extend(extractor.links)
            # HTML内に埋まったURL（markdownやJSON）も拾う
            link_candidates.extend(_markdown_links(html))

        for raw in link_candidates:
            href = _normalize_url(raw)
            if not href:
                continue
            if href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
                stats.skipped += 1
                log["skipped"].append({"url": href, "reason": "skip_non_http"})
                continue
            next_url = urljoin(url, href)
            if next_url.lower().endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
                stats.skipped += 1
                log["skipped"].append({"url": next_url, "reason": "skip_asset"})
                continue
            if not _same_domain(next_url, domain):
                continue
            if not _path_allowed(next_url, base_path):
                continue
            if next_url not in visited:
                queue.append((next_url, domain, base_path, depth - 1))

    db.commit()

    if settings.agent_save_runs:
        if run_dir is None:
            run_dir = ensure_run_dir(Path(__file__).resolve().parents[2] / "runs" / "policy_crawl")
        save_json(True, run_dir / f"crawl_{party_id}.json", {"stats": stats.__dict__, "log": log})

    return stats
