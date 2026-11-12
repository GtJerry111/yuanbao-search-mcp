from yuanbao_search_mcp.models import (
    AcademicPaper,
    ArticleResult,
    WebResult,
    WebSearchResult,
    WeixinArticle,
    WeixinSearchResult,
)


def test_weixin_search_result_serializes() -> None:
    result = WeixinSearchResult(
        query="自进化",
        count=1,
        total_available=1,
        results=[
            WeixinArticle(
                title="示例",
                account="测试号",
                publish_time="2026-11-12",
                summary="摘要",
                url="https://mp.weixin.qq.com/s/abc",
                doc_id="123",
            )
        ],
    )
    data = result.model_dump(mode="json")
    assert data["results"][0]["url"] == "https://mp.weixin.qq.com/s/abc"
    assert data["warnings"] == []


def test_academic_paper_defaults() -> None:
    paper = AcademicPaper(title="A Paper")
    assert paper.authors == []
    assert paper.evidence == []
    assert paper.abstract_truncated is False


def test_article_result_requires_counts() -> None:
    article = ArticleResult(
        title="T",
        url="https://mp.weixin.qq.com/s/x",
        content="body",
        char_count=4,
        original_chars=4,
        truncated=False,
    )
    assert article.images == []
    assert article.image_count == 0


def test_web_result_defaults() -> None:
    result = WebSearchResult(
        query="q", scope="all", count=1, results=[WebResult(title="T", url="https://x")]
    )
    assert result.results[0].date_unknown is False
    assert result.related_queries == []
