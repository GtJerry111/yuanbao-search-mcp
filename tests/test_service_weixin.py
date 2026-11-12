from datetime import date

import httpx
import respx

from yuanbao_search_mcp.service import YuanbaoService, filter_by_days


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


def test_filter_by_days_marks_unknown() -> None:
    from yuanbao_search_mcp.models import WeixinArticle

    items = [
        WeixinArticle(title="new", publish_time="2026-11-12", url="https://x/1"),
        WeixinArticle(title="old", publish_time="2026-01-01", url="https://x/2"),
        WeixinArticle(title="unknown", publish_time=None, url="https://x/3"),
    ]
    kept, undated = filter_by_days(items, days=7, today=date(2026, 11, 12))
    assert [item.title for item in kept] == ["new", "unknown"]
    assert kept[1].date_unknown is True
    assert undated == 1
