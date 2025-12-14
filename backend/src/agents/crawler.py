from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Iterable, List
from urllib.parse import urljoin, urlparse

from .base import PartyDocs, PolicyDocument, ResolvedParty


class CrawlerAgent:
    """allowlistドメインの中から政策関連ページを抽出する簡易クローラ（PoC）。"""

    def __init__(self, fetcher, max_links: int = 5, max_content_len: int = 8000):
        self.fetcher = fetcher
        self.max_links = max_links
        self.max_content_len = max_content_len

    def _is_allowed(self, url: str, allowed_domains: List[str]) -> bool:
        domain = urlparse(url).netloc.lower()
        return any(domain.endswith(ad) for ad in allowed_domains if ad)

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        class LinkParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links: List[str] = []

            def handle_starttag(self, tag, attrs):
                if tag != "a":
                    return
                href = None
                for k, v in attrs:
                    if k == "href":
                        href = v
                        break
                if href:
                    self.links.append(href)

        parser = LinkParser()
        parser.feed(html)
        links = []
        for href in parser.links:
            url = href if href.startswith("http") else urljoin(base_url, href)
            links.append(url)
        # uniq while preserving order
        seen = set()
        uniq = []
        for u in links:
            if u in seen:
                continue
            seen.add(u)
            uniq.append(u)
        return uniq

    def _filter_policy_links(self, links: List[str], *, keywords: Iterable[str], allowed: List[str]) -> List[str]:
        result = []
        for link in links:
            if not self._is_allowed(link, allowed):
                continue
            if any(re.search(kw, link, re.IGNORECASE) for kw in keywords):
                result.append(link)
        return result

    def crawl(self, party: ResolvedParty, *, keywords: List[str]) -> PartyDocs:
        docs: List[PolicyDocument] = []
        try:
            html = self.fetcher.fetch(party.official_url)
        except Exception:
            return PartyDocs(party_name=party.name_ja, docs=docs)

        # 公式トップは常に含める
        links = [party.official_url]
        # トップページからリンク抽出し、キーワードやallowlistでフィルタ
        all_links = self._extract_links(html, party.official_url)
        filtered = self._filter_policy_links(all_links, keywords=keywords, allowed=party.allowed_domains)
        links.extend(filtered[: self.max_links])

        for link in links:
            try:
                content = self.fetcher.fetch(link)
            except Exception:
                continue
            truncated = content[: self.max_content_len]
            docs.append(PolicyDocument(url=link, content=truncated))
        return PartyDocs(party_name=party.name_ja, docs=docs)
