"""High-level operations exposed by the MCP tools."""

from __future__ import annotations

import asyncio
from datetime import date
from urllib.parse import urlparse

from .academic import AcademicSession
from .client import (
    ArticleUnavailableError,
    HttpClient,
    TTLCache,
    UpstreamBlockedError,
    UpstreamError,
)
from .config import WECHAT_USER_AGENT, Settings
from .models import (
    AcademicPaper,
    AcademicSearchResult,
    ArticleResult,
    WebResult,
    WebSearchResult,
    WeixinArticle,
    WeixinSearchResult,
)
from .parsers import (
    extract_initial_cards,
    is_article_error_page,
    is_blocked_page,
    normalize_url,
    parse_date,
    parse_web_cards,
    parse_weixin_article,
    parse_weixin_cards,
)


def filter_by_days(
    items: list[WeixinArticle] | list[WebResult],
    days: int,
    today: date | None = None,
) -> tuple[list[WeixinArticle] | list[WebResult], int]:
    """Keep items from the last N calendar days including today.

    Undated items are kept and flagged with ``date_unknown=True``; the second
    return value is the number of such items.
    """
    cutoff = (today or date.today()).toordinal() - (days - 1)
    kept = []
    undated = 0
    for item in items:
        parsed = (
            parse_date(item.publish_time)
            if isinstance(item, WeixinArticle)
            else parse_date(item.date)
        )
        if parsed is None:
            item.date_unknown = True
            undated += 1
            kept.append(item)
        elif parsed.toordinal() >= cutoff:
            kept.append(item)
    return kept, undated


def sort_by_date(
    items: list[WeixinArticle] | list[WebResult],
) -> list[WeixinArticle] | list[WebResult]:
    def key(item: WeixinArticle | WebResult) -> tuple[int, int]:
        parsed = (
            parse_date(item.publish_time)
            if isinstance(item, WeixinArticle)
            else parse_date(item.date)
        )
        return (0 if parsed else 1, -(parsed.toordinal() if parsed else 0))

    return sorted(items, key=key)


class YuanbaoService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpClient(settings)
        self._weixin_cache: TTLCache[WeixinSearchResult] = TTLCache(settings.cache_ttl)
        self._web_cache: TTLCache[WebSearchResult] = TTLCache(settings.cache_ttl)
        self._article_cache: TTLCache[ArticleResult] = TTLCache(settings.article_cache_ttl)
        self._academic_cache: TTLCache[AcademicSearchResult] = TTLCache(
            settings.academic_cache_ttl
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def search_weixin(
        self,
        query: str,
        account: str | None = None,
        limit: int = 20,
        sort: str = "relevance",
        days: int | None = None,
    ) -> WeixinSearchResult:
        query = (query or "").strip()
        account = (account or "").strip() or None
        if not query and not account:
            raise ValueError("query or account is required")

        limit = max(1, min(limit, self.settings.weixin_max_results))
        if sort not in ("relevance", "date"):
            raise ValueError("sort must be relevance or date")
        if days is not None and days < 1:
            raise ValueError("days must be >= 1")
        cache_key = repr(("wx", query, account, limit, sort, days))
        cached = self._weixin_cache.get(cache_key)
        if cached is not None:
            return cached

        upstream_query = " ".join(part for part in (account, query) if part)
        html = await self.http.get(
            "https://so.qq.com/isearch",
            params={"query": upstream_query, "tab": "weixin_article"},
        )
        if is_blocked_page(html):
            raise UpstreamBlockedError("Yuanbao returned an anti-crawl page")

        articles = parse_weixin_cards(extract_initial_cards(html))
        if account:
            needle = account.casefold()
            articles = [
                item
                for item in articles
                if item.account and needle in item.account.casefold()
            ]

        warnings: list[str] = []
        if days is not None:
            articles, undated = filter_by_days(articles, days)
            if undated:
                warnings.append(
                    f"{undated} result(s) had no publish date and were kept with date_unknown=true."
                )
        total_available = len(articles)
        if sort == "date":
            articles = sort_by_date(articles)  # type: ignore[assignment]

        results = articles[:limit]
        if not results:
            warnings.append("No matching WeChat articles were found.")

        result = WeixinSearchResult(
            query=query,
            account=account,
            count=len(results),
            total_available=total_available,
            results=results,
            warnings=warnings,
        )
        self._weixin_cache.set(cache_key, result)
        return result

    async def read_article(self, url: str, max_chars: int = 20000) -> ArticleResult:
        parsed_url = urlparse(url)
        if (
            parsed_url.scheme not in ("http", "https")
            or parsed_url.hostname != "mp.weixin.qq.com"
        ):
            raise ValueError("Only mp.weixin.qq.com article URLs are supported")

        max_chars = max(1000, min(max_chars, 100000))
        cache_key = f"article:{url}|{max_chars}"
        cached = self._article_cache.get(cache_key)
        if cached is not None:
            return cached

        html = await self.http.get(
            url,
            headers={"user-agent": WECHAT_USER_AGENT, "referer": "https://so.qq.com/"},
            max_bytes=15_000_000,
        )
        if is_blocked_page(html):
            raise ArticleUnavailableError("WeChat returned a verification page")
        if is_article_error_page(html) and "#js_content" not in html:
            raise ArticleUnavailableError("Article is deleted, restricted, or requires WeChat")

        parsed = parse_weixin_article(html)
        original_chars = len(parsed.content)
        content = parsed.content
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars].rsplit("\n\n", 1)[0] or content[:max_chars]
            truncated = True

        result = ArticleResult(
            title=parsed.title,
            account=parsed.account,
            publish_time=parsed.publish_time,
            url=normalize_url(url),
            content=content,
            char_count=len(content),
            original_chars=original_chars,
            truncated=truncated,
            images=parsed.images[:50],
            image_count=len(parsed.images),
        )
        self._article_cache.set(cache_key, result)
        return result

    async def search_web(
        self,
        query: str,
        limit: int = 10,
        scope: str = "all",
        sort: str = "relevance",
        days: int | None = None,
    ) -> WebSearchResult:
        query = (query or "").strip()
        if not query:
            raise ValueError("query is required")
        if scope not in ("all", "gov", "media"):
            raise ValueError("scope must be all, gov, or media")

        limit = max(1, min(limit, self.settings.web_max_results))
        if sort not in ("relevance", "date"):
            raise ValueError("sort must be relevance or date")
        if days is not None and days < 1:
            raise ValueError("days must be >= 1")
        cache_key = repr(("web", query, limit, scope, sort, days))
        cached = self._web_cache.get(cache_key)
        if cached is not None:
            return cached

        html = await self.http.get(
            "https://so.qq.com/isearch",
            params={"query": query, "tab": scope},
        )
        if is_blocked_page(html):
            raise UpstreamBlockedError("Yuanbao returned an anti-crawl page")

        results, related = parse_web_cards(extract_initial_cards(html))
        warnings: list[str] = []
        if days is not None:
            results, undated = filter_by_days(results, days)
            if undated:
                warnings.append(
                    f"{undated} result(s) had no publish date and were kept with date_unknown=true."
                )
        if sort == "date":
            results = sort_by_date(results)  # type: ignore[assignment]

        results = results[:limit]
        if not results:
            warnings.append("No matching web results were found.")

        result = WebSearchResult(
            query=query,
            scope=scope,  # type: ignore[arg-type]
            count=len(results),
            results=results,
            related_queries=related,
            warnings=warnings,
        )
        self._web_cache.set(cache_key, result)
        return result

    async def search_academic(
        self,
        query: str,
        limit: int = 10,
        include_summary: bool = False,
        summary_timeout: float = 45.0,
        include_subquestions: bool = True,
    ) -> AcademicSearchResult:
        query = (query or "").strip()
        if not query:
            raise ValueError("query is required")

        limit = max(1, min(limit, self.settings.academic_max_papers))
        summary_timeout = max(0.1, min(summary_timeout, 120.0))
        cache_key = repr(
            (
                "academic",
                query,
                limit,
                include_summary,
                summary_timeout,
                include_subquestions,
            )
        )
        cached = self._academic_cache.get(cache_key)
        if cached is not None:
            return cached

        session = AcademicSession(self.http, query)
        await session.create()

        sup_task = asyncio.create_task(session.fetch_sup())
        subq_task = (
            asyncio.create_task(session.fetch_sub_questions())
            if include_subquestions
            else None
        )

        # Wait for get_sup to start the academic generation before polling summary frames.
        sup_result = (await asyncio.gather(sup_task, return_exceptions=True))[0]

        summary_task = (
            asyncio.create_task(session.fetch_summary(summary_timeout))
            if include_summary
            else None
        )

        pending = [task for task in (subq_task, summary_task) if task is not None]
        pending_results = await asyncio.gather(*pending, return_exceptions=True)

        core_papers: list[AcademicPaper] = []
        sub_questions = []
        summary = None
        summary_truncated = False
        summary_chars = 0
        warnings: list[str] = []

        if isinstance(sup_result, Exception):
            warnings.append(f"Core papers could not be loaded: {sup_result}")
        else:
            core_papers = sup_result[:limit]

        index = 0
        if subq_task is not None:
            if isinstance(pending_results[index], Exception):
                warnings.append(f"Sub-questions could not be loaded: {pending_results[index]}")
            else:
                sub_questions = pending_results[index]
            index += 1

        figures_omitted = False
        if summary_task is not None:
            if isinstance(pending_results[index], Exception):
                warnings.append(f"AI summary failed: {pending_results[index]}")
            else:
                (
                    summary,
                    summary_truncated,
                    summary_chars,
                    figures_omitted,
                ) = pending_results[index]
                if figures_omitted:
                    warnings.append("Summary figure placeholders were omitted.")

        if not core_papers and not sub_questions:
            raise UpstreamError("Academic search failed for both papers and sub-questions")

        result = AcademicSearchResult(
            query=query,
            core_papers=core_papers,
            sub_questions=sub_questions,
            summary=summary,
            summary_truncated=summary_truncated,
            summary_char_count=summary_chars,
            warnings=warnings,
        )
        self._academic_cache.set(cache_key, result)
        return result
