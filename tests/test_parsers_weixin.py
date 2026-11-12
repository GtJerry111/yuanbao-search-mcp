from datetime import date
from pathlib import Path

from yuanbao_search_mcp.parsers import (
    extract_initial_cards,
    parse_date,
    parse_weixin_cards,
    strip_highlight,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_strip_highlight() -> None:
    assert strip_highlight("递归\ue40a自进化\ue40b") == "递归自进化"


def test_parse_date() -> None:
    assert parse_date("2026-11-12") == date(2026, 11, 12)
    assert parse_date("2026/11/12 08:30:00") == date(2026, 11, 12)
    assert parse_date("") is None
    assert parse_date("not a date") is None


def test_extract_weixin_cards() -> None:
    html = (FIXTURES / "weixin_search.html").read_text(encoding="utf-8")
    cards = extract_initial_cards(html)
    assert len(cards) >= 20

    articles = parse_weixin_cards(cards)
    # The recorded fixture contains 26 WeChat cards (the brief said 28).
    assert len(articles) == 26
    assert articles[0].account == "词元潮汐"
    assert "自进化" in articles[0].title
    assert articles[0].url.startswith("https://mp.weixin.qq.com/")
    assert "\ue40a" not in articles[0].title
    assert "\ue40b" not in (articles[0].summary or "")


def test_weixin_cards_deduplicate() -> None:
    html = (FIXTURES / "weixin_search.html").read_text(encoding="utf-8")
    cards = extract_initial_cards(html)
    articles = parse_weixin_cards(cards + cards)
    assert len(articles) == 26
