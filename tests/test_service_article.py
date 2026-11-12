import httpx
import pytest
import respx

from yuanbao_search_mcp.client import ArticleUnavailableError
from yuanbao_search_mcp.service import YuanbaoService

ARTICLE_URL = "https://mp.weixin.qq.com/s?__biz=abc&mid=1&idx=1&sn=xyz"

_LONG = "Long paragraph. " * 200
ARTICLE_HTML = f"""
<!DOCTYPE html><html><body>
<h1 id="activity-name">Title</h1>
<span id="js_name">Account</span>
<em id="publish_time">2026-11-12</em>
<div id="js_content">
  <p>Paragraph one.</p>
  <p>Paragraph two.</p>
  <p>{_LONG}</p>
  <img data-src="https://mmbiz.qpic.cn/a.jpg" />
</div>
</body></html>
"""


@respx.mock
async def test_read_article(settings) -> None:
    respx.get(ARTICLE_URL).mock(return_value=httpx.Response(200, text=ARTICLE_HTML))
    service = YuanbaoService(settings)
    try:
        result = await service.read_article(ARTICLE_URL)
        assert result.title == "Title"
        assert result.account == "Account"
        assert result.char_count > 0
        assert result.images == ["https://mmbiz.qpic.cn/a.jpg"]
        assert result.truncated is False
    finally:
        await service.aclose()


@respx.mock
async def test_read_article_truncates(settings) -> None:
    respx.get(ARTICLE_URL).mock(return_value=httpx.Response(200, text=ARTICLE_HTML))
    service = YuanbaoService(settings)
    try:
        result = await service.read_article(ARTICLE_URL, max_chars=1000)
        assert result.original_chars > result.char_count
        assert result.truncated is True
    finally:
        await service.aclose()


async def test_read_article_rejects_non_weixin(settings) -> None:
    service = YuanbaoService(settings)
    try:
        with pytest.raises(ValueError):
            await service.read_article("https://example.com/article")
    finally:
        await service.aclose()


@respx.mock
async def test_read_article_blocked(settings) -> None:
    respx.get(ARTICLE_URL).mock(
        return_value=httpx.Response(200, text="<html><body>环境异常</body></html>")
    )
    service = YuanbaoService(settings)
    try:
        with pytest.raises(ArticleUnavailableError):
            await service.read_article(ARTICLE_URL)
    finally:
        await service.aclose()
