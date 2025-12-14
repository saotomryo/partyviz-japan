from __future__ import annotations

import httpx


class HttpxFetcher:
    """実際にHTTP GETでページを取得するフェッチャ。"""

    def __init__(self, timeout: int = 20):
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def fetch(self, url: str, *, timeout: int | None = None) -> str:
        resp = self.client.get(url, timeout=timeout or self.client.timeout)
        resp.raise_for_status()
        return resp.text
