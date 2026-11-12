import json
from datetime import date, timedelta

import httpx
import pytest
import respx

from yuanbao_search_mcp.service import YuanbaoService, filter_by_days


def _rsc_html(cards: list[dict]) -> str:
    payload = json.dumps({"initialCards": cards}, ensure_ascii=False)
    return f"<script>self.__next_f.push([1,{json.dumps(payload)}])</script>"


def _weixin_card(title: str, publish_time: str | None) -> dict:
    return {
        "type": "card",
        "data": {
            "cardName": "card-common/card30010612",
            "vm": {
                "isWxmpTab": True,
                "title": title,
                "authorName": "Test Account",
                "publishTime": publish_time,
                "docId": title,
                "jumpUrl": f"https://mp.weixin.qq.com/s/{title}",
            },
        },
    }


@respx.mock
async def test_search_weixin_defaults(settings, weixin_search_html) -> None:
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=weixin_search_html)
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_weixin("自进化")
        assert result.count == 20
        assert result.total_available == 26
        assert result.results[0].account == "词元潮汐"
        assert result.results[0].publish_time
        assert result.warnings == []
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_account_filter(settings, weixin_search_html) -> None:
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=weixin_search_html)
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_weixin("", account="词元潮汐")
        assert result.count >= 1
        assert all("词元潮汐" in (item.account or "") for item in result.results)
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_query_composition(settings, weixin_search_html) -> None:
    route = respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=weixin_search_html)
    )
    service = YuanbaoService(settings)
    try:
        await service.search_weixin("自进化", account="词元潮汐")
        assert route.calls[0].request.url.params["query"] == "词元潮汐 自进化"
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_account_is_case_insensitive(settings, weixin_search_html) -> None:
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=weixin_search_html)
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_weixin("自进化", account="paperagent")
        assert result.count >= 1
        assert all("paperagent" in (item.account or "").casefold() for item in result.results)
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_limit_clamped(settings, weixin_search_html) -> None:
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=weixin_search_html)
    )
    clipped_settings = settings.model_copy(update={"weixin_max_results": 5})
    service = YuanbaoService(clipped_settings)
    try:
        result = await service.search_weixin("自进化", limit=100)
        assert result.count == 5
        assert result.total_available == 26
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_sort_date_undated_last(settings) -> None:
    html = _rsc_html(
        [
            _weixin_card("middle", "2026-11-08"),
            _weixin_card("newest", "2026-11-10"),
            _weixin_card("undated", None),
            _weixin_card("oldest", "2026-11-01"),
        ]
    )
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=html)
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_weixin("test", sort="date")
        assert [item.title for item in result.results] == [
            "newest",
            "middle",
            "oldest",
            "undated",
        ]
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_days_filter_and_warning(settings) -> None:
    recent = date.today().isoformat()
    old = (date.today() - timedelta(days=30)).isoformat()
    html = _rsc_html(
        [
            _weixin_card("recent", recent),
            _weixin_card("old", old),
            _weixin_card("undated", None),
        ]
    )
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=html)
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_weixin("test", days=7)
        assert [item.title for item in result.results] == ["recent", "undated"]
        assert result.results[1].date_unknown is True
        assert result.total_available == 2
        assert any("1 result(s) had no publish date" in warning for warning in result.warnings)
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_block_marker_in_results(settings) -> None:
    html = _rsc_html([_weixin_card("环境异常与操作频繁测试", "2026-11-12")])
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=html)
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_weixin("环境异常")
        assert result.count == 1
        assert result.results[0].title == "环境异常与操作频繁测试"
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_cache_hits(settings, weixin_search_html) -> None:
    route = respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=weixin_search_html)
    )
    cached_settings = settings.model_copy(update={"cache_ttl": 60})
    service = YuanbaoService(cached_settings)
    try:
        first = await service.search_weixin("自进化")
        second = await service.search_weixin("自进化")
        assert first.count == second.count
        assert route.call_count == 1
    finally:
        await service.aclose()


async def test_search_weixin_requires_query_or_account(settings) -> None:
    service = YuanbaoService(settings)
    try:
        with pytest.raises(ValueError):
            await service.search_weixin("")
        with pytest.raises(ValueError):
            await service.search_weixin("", account="  ")
    finally:
        await service.aclose()


async def test_search_weixin_rejects_days_zero(settings) -> None:
    service = YuanbaoService(settings)
    try:
        with pytest.raises(ValueError):
            await service.search_weixin("自进化", days=0)
    finally:
        await service.aclose()


def test_filter_by_days_marks_unknown() -> None:
    from yuanbao_search_mcp.models import WeixinArticle

    items = [
        WeixinArticle(title="new", publish_time="2026-11-12", url="https://x/1"),
        WeixinArticle(title="boundary", publish_time="2026-11-06", url="https://x/2"),
        WeixinArticle(title="too-old", publish_time="2026-11-05", url="https://x/3"),
        WeixinArticle(title="old", publish_time="2026-01-01", url="https://x/4"),
        WeixinArticle(title="unknown", publish_time=None, url="https://x/5"),
    ]
    kept, undated = filter_by_days(items, days=7, today=date(2026, 11, 12))
    assert [item.title for item in kept] == ["new", "boundary", "unknown"]
    assert kept[2].date_unknown is True
    assert undated == 1
