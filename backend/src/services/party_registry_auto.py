from __future__ import annotations

from dataclasses import asdict
from typing import List, Tuple
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..agents.discovery import DiscoveryAgent
from ..agents.llm_search import GeminiLLMSearchClient, OpenAILLMSearchClient
from ..schemas import PartyCreate, PartyStatusEnum
from ..settings import settings
from . import party_registry


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    parsed = urlparse(u)
    if parsed.scheme:
        return u
    return f"https://{u.lstrip('/')}"


def _derive_allowed_domains(official_url: str) -> list[str]:
    u = _normalize_url(official_url)
    host = urlparse(u).netloc.lower()
    if not host:
        return []
    if ":" in host:
        host = host.split(":", 1)[0]
    domains = [host]
    if host.startswith("www."):
        domains.append(host.removeprefix("www."))
    return list(dict.fromkeys([d for d in domains if d]))


def discover_parties_via_llm(
    *,
    query: str,
    provider: str = "auto",
    openai_model: str | None = None,
    gemini_model: str | None = None,
    limit: int = 50,
    debug: bool = False,
) -> Tuple[str, list[PartyCreate], dict]:
    """
    LLMのweb検索/groundingで政党と公式URL候補を収集し、PartyCreateのリストへ変換する。
    Returns: (used_provider, payloads, debug_info)
    """
    provider = (provider or "auto").lower()

    used_provider: str | None = None
    search_client = None

    if provider in {"auto", "gemini"} and settings.gemini_api_key:
        used_provider = "gemini"
        search_client = GeminiLLMSearchClient(
            api_key=settings.gemini_api_key,
            model=gemini_model or settings.gemini_search_model,
            debug=debug,
        )
    elif provider in {"auto", "openai"} and settings.openai_api_key:
        used_provider = "openai"
        search_client = OpenAILLMSearchClient(
            api_key=settings.openai_api_key,
            model=openai_model or settings.openai_search_model,
            debug=debug,
        )
    else:
        raise ValueError("No available LLM provider for party discovery")

    agent = DiscoveryAgent(search_client=search_client)
    candidates = agent.run(query=query)[: max(1, int(limit))]

    debug_info = {
        "query": query,
        "provider": used_provider,
        "model": getattr(search_client, "model", None),
        "candidates": [asdict(c) for c in candidates],
        "last_error": getattr(search_client, "last_error", None),
    }

    payloads: list[PartyCreate] = []
    for c in candidates:
        official_url = _normalize_url(c.candidate_url)
        if not official_url:
            continue
        allowed_domains = _derive_allowed_domains(official_url)
        payloads.append(
            PartyCreate(
                name_ja=c.name_ja,
                official_home_url=official_url,
                allowed_domains=allowed_domains,
                confidence=0.5,
                status=PartyStatusEnum.candidate,
                evidence={
                    "source": "llm_discovery",
                    "query": query,
                    "candidate": asdict(c),
                    "llm_provider": used_provider,
                    "llm_model": getattr(search_client, "model", None),
                },
            )
        )

    return used_provider or provider, payloads, debug_info


def discover_and_upsert_parties(
    db: Session,
    *,
    query: str,
    provider: str = "auto",
    openai_model: str | None = None,
    gemini_model: str | None = None,
    limit: int = 50,
    dry_run: bool = False,
    debug: bool = False,
) -> tuple[str, list, dict]:
    used_provider, payloads, debug_info = discover_parties_via_llm(
        query=query,
        provider=provider,
        openai_model=openai_model,
        gemini_model=gemini_model,
        limit=limit,
        debug=debug,
    )

    results = []
    counts = {"found": len(payloads), "created": 0, "updated": 0, "skipped": 0}
    for p in payloads:
        if dry_run:
            counts["skipped"] += 1
            results.append({"action": "skipped", "name_ja": p.name_ja, "official_home_url": p.official_home_url})
            continue
        _, action = party_registry.upsert_party(db, p)
        counts[action] += 1
        results.append({"action": action, "name_ja": p.name_ja, "official_home_url": p.official_home_url})

    return used_provider, results, {**counts, "debug": debug_info}
