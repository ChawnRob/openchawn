"""Web search tool — Perplexity or Tavily providers (MVP snippets + sources)."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from app.settings import Settings, get_settings

logger = logging.getLogger("openchawn.web_search")

_SEARCH_TIMEOUT_SEC = 12.0


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


def _provider_name(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return (s.web_search_provider or "perplexity").strip().lower()


def is_web_search_provider_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    provider = _provider_name(s)
    if provider == "tavily":
        return bool((s.tavily_api_key or "").strip())
    if provider == "perplexity":
        return bool((s.perplexity_api_key or "").strip())
    return False


def is_web_search_runtime_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.web_search_enabled) and is_web_search_provider_configured(s)


def get_web_search_status(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    provider = _provider_name(s)
    configured = is_web_search_provider_configured(s)
    return {
        "enabled": bool(s.web_search_enabled) and configured,
        "provider": provider,
        "configured": configured,
        "max_results": int(s.web_search_max_results or 5),
    }


def _clamp_limit(limit: int, settings: Settings) -> int:
    cap = max(1, int(settings.web_search_max_results or 5))
    return max(1, min(int(limit or cap), cap))


def _hostname_title(url: str) -> str:
    try:
        host = urlparse(url).netloc or url
        return host.replace("www.", "") or url
    except Exception:
        return url


def _search_perplexity(query: str, *, limit: int, settings: Settings) -> list[WebSearchResult]:
    api_key = (settings.perplexity_api_key or "").strip()
    if not api_key:
        return []
    base = (settings.perplexity_base_url or "https://api.perplexity.ai").rstrip("/")
    model = (settings.perplexity_model or "llama-3.1-sonar-small-128k-online").strip()
    url = f"{base}/chat/completions"
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Search the web and list factual sources for: {query}. "
                            "Be concise; focus on current public information."
                        ),
                    }
                ],
            },
            timeout=_SEARCH_TIMEOUT_SEC,
        )
        if not r.ok:
            logger.warning(
                "web_search perplexity failed status=%s body=%s",
                r.status_code,
                (r.text or "")[:200],
            )
            return []
        data = r.json()
    except Exception as exc:
        logger.warning("web_search perplexity exception=%s", exc.__class__.__name__)
        return []

    out: list[WebSearchResult] = []
    seen: set[str] = set()

    for item in data.get("search_results") or []:
        if not isinstance(item, dict):
            continue
        link = str(item.get("url") or "").strip()
        if not link or link in seen:
            continue
        seen.add(link)
        title = str(item.get("title") or _hostname_title(link)).strip()
        snippet = str(item.get("snippet") or item.get("description") or "").strip()
        out.append(WebSearchResult(title=title, url=link, snippet=snippet))
        if len(out) >= limit:
            return out

    for link in data.get("citations") or []:
        link = str(link or "").strip()
        if not link or link in seen:
            continue
        if not re.match(r"^https?://", link, re.IGNORECASE):
            continue
        seen.add(link)
        out.append(
            WebSearchResult(
                title=_hostname_title(link),
                url=link,
                snippet="",
            )
        )
        if len(out) >= limit:
            break

    return out


def _search_tavily(query: str, *, limit: int, settings: Settings) -> list[WebSearchResult]:
    api_key = (settings.tavily_api_key or "").strip()
    if not api_key:
        return []
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": limit,
                "include_answer": False,
            },
            timeout=_SEARCH_TIMEOUT_SEC,
        )
        if not r.ok:
            logger.warning(
                "web_search tavily failed status=%s body=%s",
                r.status_code,
                (r.text or "")[:200],
            )
            return []
        data = r.json()
    except Exception as exc:
        logger.warning("web_search tavily exception=%s", exc.__class__.__name__)
        return []

    out: list[WebSearchResult] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        link = str(item.get("url") or "").strip()
        if not link:
            continue
        out.append(
            WebSearchResult(
                title=str(item.get("title") or _hostname_title(link)).strip(),
                url=link,
                snippet=str(item.get("content") or "").strip()[:500],
            )
        )
        if len(out) >= limit:
            break
    return out


def web_search_sync(query: str, limit: int = 5, settings: Settings | None = None) -> list[WebSearchResult]:
    """Synchronous web search for the chat pipeline."""
    q = (query or "").strip()
    if not q:
        return []
    s = settings or get_settings()
    if not is_web_search_runtime_enabled(s):
        return []
    lim = _clamp_limit(limit, s)
    provider = _provider_name(s)
    if provider == "tavily":
        return _search_tavily(q, limit=lim, settings=s)
    return _search_perplexity(q, limit=lim, settings=s)


async def web_search(query: str, limit: int = 5) -> list[WebSearchResult]:
    """Async wrapper (runs sync HTTP in a worker thread)."""
    return await asyncio.to_thread(web_search_sync, query, limit)


def format_web_search_results_block(results: list[WebSearchResult]) -> str:
    if not results:
        return "WEB_SEARCH_RESULTS:\n(no usable results — search tool returned empty)"
    lines = ["WEB_SEARCH_RESULTS:"]
    for i, hit in enumerate(results, start=1):
        lines.append(f"{i}. Title: {hit.title}")
        lines.append(f"   URL: {hit.url}")
        lines.append(f"   Snippet: {hit.snippet or '(no snippet)'}")
    return "\n".join(lines)


WEB_SEARCH_RUNTIME_INSTRUCTION = (
    "Web search results are provided below by OpenChawn runtime. Use them to answer. "
    "Cite sources by title or URL. If results are empty, say the search tool returned no usable result. "
    "You can perform a web search via OpenChawn when the tool is available — you cannot browse "
    "arbitrary sites freely, download files, or crawl entire websites."
)
