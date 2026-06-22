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
    source_index: int = 0


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


def _assign_source_indices(results: list[WebSearchResult]) -> list[WebSearchResult]:
    return [
        WebSearchResult(
            title=r.title,
            url=r.url,
            snippet=r.snippet,
            source_index=i,
        )
        for i, r in enumerate(results, start=1)
    ]


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
        return _assign_source_indices(_search_tavily(q, limit=lim, settings=s))
    return _assign_source_indices(_search_perplexity(q, limit=lim, settings=s))


async def web_search(query: str, limit: int = 5) -> list[WebSearchResult]:
    """Async wrapper (runs sync HTTP in a worker thread)."""
    return await asyncio.to_thread(web_search_sync, query, limit)


def format_web_search_results_block(results: list[WebSearchResult]) -> str:
    if not results:
        return "WEB_SEARCH_RESULTS:\n(no usable results — search tool returned empty)"
    lines = ["WEB_SEARCH_RESULTS:"]
    for i, hit in enumerate(results, start=1):
        idx = hit.source_index or i
        lines.append(f"[{idx}] source_index: {idx}")
        lines.append(f"    title: {hit.title}")
        lines.append(f"    url: {hit.url}")
        lines.append(f"    snippet: {hit.snippet or '(no snippet)'}")
    return "\n".join(lines)


WEB_SEARCH_RUNTIME_INSTRUCTION = (
    "Web search results are provided below by OpenChawn runtime (Tavily/Perplexity snippets only). "
    "You can perform a web search via OpenChawn when the tool is available — you cannot browse "
    "arbitrary sites freely, download files, or crawl entire websites."
)

WEB_SEARCH_GROUNDING_INSTRUCTION = (
    "WEB_SEARCH_GROUNDING_RULES (mandatory when WEB_SEARCH_RESULTS is non-empty):\n"
    "- Facts must come explicitly from the provided source snippets only — quote or paraphrase "
    "what is in snippet text for the matching source_index.\n"
    "- Competitors, risks, opportunities, pricing models (freemium, marketplace), integrations "
    "(Zapier, n8n, Airflow, etc.), and recommendations MUST be labeled as inferences in "
    "## Inférences if they are not explicitly stated in a snippet.\n"
    "- Never present an inference or hypothesis as a confirmed fact.\n"
    "- If information is not found in the snippets, write exactly: "
    "Non trouvé dans les sources fournies. (or English equivalent when answering in English).\n"
    "- Do NOT use phrasing like the official site says or according to the website unless "
    "the snippet text literally contains that information — you only have search snippets, not full pages.\n"
    "- Always end with a ## Sources utilisées section listing every source used.\n"
    "- Use this exact markdown structure for web-based analyses:\n\n"
    "## Faits observés\n"
    "- ... (each bullet must map to a source_index)\n\n"
    "## Inférences\n"
    "- ... (reasoning not directly in snippets)\n\n"
    "## Hypothèses non confirmées\n"
    "- ... (speculation clearly marked)\n\n"
    "## Analyse / Recommandations\n"
    "- ...\n\n"
    "## Sources utilisées\n"
    "1. Title — URL\n"
)

WEB_SEARCH_EMPTY_RESULTS_INSTRUCTION = (
    "WEB_SEARCH_GROUNDING_RULES (search attempted, no usable snippets):\n"
    "- Tell the user the search tool did not return enough elements to ground an analysis.\n"
    "- Do not invent facts about the website or topic.\n"
    "- Do not list competitors, features, or business model details from general knowledge.\n"
    "- Suggest retrying with a more specific query if helpful."
)


def build_web_search_system_addon(*, has_results: bool) -> str:
    """Conditional system instructions when web search ran in this turn."""
    if has_results:
        return f"{WEB_SEARCH_RUNTIME_INSTRUCTION}\n\n{WEB_SEARCH_GROUNDING_INSTRUCTION}"
    return f"{WEB_SEARCH_RUNTIME_INSTRUCTION}\n\n{WEB_SEARCH_EMPTY_RESULTS_INSTRUCTION}"


WEB_CAPABILITY_TRUTHFULNESS_INSTRUCTION = (
    "WEB_CAPABILITY_TRUTHFULNESS (web search is runtime-enabled but WEB_SEARCH_RESULTS is NOT in this turn):\n"
    "- OpenChawn can run public web search (Tavily/Perplexity snippets) when the user request matches the "
    "web-search intent router.\n"
    "- NEVER claim you lack a web search tool, browsing tool, or navigation capability in this deployment.\n"
    "- If the user expected live web data but this turn did not inject WEB_SEARCH_RESULTS, explain that public "
    "search runs only when the request triggers the tool — do not deny that the tool exists.\n"
    "- Use wording equivalent to (adapt to OUTPUT LANGUAGE): "
    "\"Je peux rechercher des informations publiques via OpenChawn quand la demande déclenche l'outil web, "
    "mais je ne peux pas accéder aux comptes privés, contenus derrière connexion ou messages personnels.\"\n"
)

WEB_PROTECTED_REQUEST_INSTRUCTION = (
    "WEB_PROTECTED_REQUEST (private / authenticated access — web search must NOT run):\n"
    "- Refuse politely. Do not log in, read private messages, open the user's personal accounts, or scrape "
    "private profiles.\n"
    "- NEVER claim you lack a web search tool in this deployment — public search is available for open "
    "information when the request triggers the tool.\n"
    "- Use wording equivalent to (adapt to OUTPUT LANGUAGE): "
    "\"Je peux rechercher des informations publiques via OpenChawn quand la demande déclenche l'outil web, "
    "mais je ne peux pas accéder aux comptes privés, contenus derrière connexion ou messages personnels.\"\n"
)


def build_web_capability_system_addon(*, protected_request: bool = False) -> str:
    """System instructions when web search is enabled but did not run this turn."""
    if protected_request:
        return WEB_PROTECTED_REQUEST_INSTRUCTION
    return WEB_CAPABILITY_TRUTHFULNESS_INSTRUCTION
