import pytest

from yuanbao_search_mcp.client import ArticleUnavailableError
from yuanbao_search_mcp.parsers import parse_weixin_article

ARTICLE_HTML = """
<!DOCTYPE html>
<html><body>
<h1 id="activity-name">Test Article</h1>
<span id="js_name">Test Account</span>
<em id="publish_time">2026-11-12</em>
<div id="js_content">
  <p>First paragraph.</p>
  <h2>Section</h2>
  <p>Second paragraph with <strong>bold</strong>.</p>
  <ul><li>Item 1</li><li>Item 2</li></ul>
  <blockquote>Quoted text.</blockquote>
  <img data-src="https://mmbiz.qpic.cn/a.jpg" />
  <img src="https://wx.qlogo.cn/avatar.jpg" />
  <p>Last paragraph.</p>
</div>
</body></html>
"""


def test_parse_article_fields() -> None:
    article = parse_weixin_article(ARTICLE_HTML)
    assert article.title == "Test Article"
    assert article.account == "Test Account"
    assert article.publish_time == "2026-11-12"
    assert "First paragraph." in article.content
    assert "## Section" in article.content
    assert "- Item 1" in article.content
    assert "> Quoted text." in article.content
    assert article.images == ["https://mmbiz.qpic.cn/a.jpg"]
    assert article.content.endswith("Last paragraph.")


def test_article_error_page() -> None:
    with pytest.raises(ArticleUnavailableError):
        parse_weixin_article("<html><body>参数错误</body></html>")
