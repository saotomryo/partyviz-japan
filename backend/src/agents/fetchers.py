from __future__ import annotations

import httpx

from ..settings import settings


class HttpxFetcher:
    """実際にHTTP GETでページを取得するフェッチャ。"""

    def __init__(self, timeout: int = 20):
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": settings.http_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": settings.http_accept_language,
            },
        )

    def fetch(self, url: str, *, timeout: int | None = None) -> str:
        resp = self.client.get(url, timeout=timeout or self.client.timeout)
        resp.raise_for_status()
        return resp.text
