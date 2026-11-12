from yuanbao_search_mcp.parsers import parse_web_cards


def test_parse_web_cards_and_related() -> None:
    cards = [
        {
            "data": {
                "cardName": "card-pc/card_normal_result",
                "vm": {
                    "title": "Result A",
                    "url": "https://a.example.com/page",
                    "sourcename": "Site A",
                    "date": "2026-11-12",
                    "content": "Snippet A",
                },
            }
        },
        {
            "data": {
                "cardName": "card-pc/card30010588",
                "vm": {
                    "title": "Result B",
                    "url": "https://b.example.com/page",
                    "sourcename": "Site B",
                    "date": "",
                    "content": "Snippet B",
                },
            }
        },
        {
            "data": {
                "cardName": "card-pc/card_bottom_hint",
                "vm": {"hints": [{"text": "related 1"}, {"text": "related 2"}]},
            }
        },
    ]

    results, related = parse_web_cards(cards)
    assert [item.title for item in results] == ["Result A", "Result B"]
    assert results[0].date == "2026-11-12"
    assert results[0].date_unknown is False
    assert results[1].date_unknown is True
    assert related == ["related 1", "related 2"]


def test_parse_web_cards_deduplicates_urls() -> None:
    card = {
        "data": {
            "cardName": "card-pc/card_normal_result",
            "vm": {"title": "A", "url": "https://a.example.com", "content": "x"},
        }
    }
    results, related = parse_web_cards([card, card])
    assert len(results) == 1
    assert related == []


def test_web_card_wechat_and_hints() -> None:
    cards = [
        {
            "data": {
                "cardName": "card-common/card30010608",
                "vm": {
                    "title": "WeChat Article",
                    "h5Url": "http://mp.weixin.qq.com/s?x=1",
                    "showname": "Account",
                    "publishTime": "2026-11-12",
                    "content": "Snippet",
                },
            }
        },
        {
            "data": {
                "cardName": "card-pc/card_hint_middle",
                "vm": {"hints": [{"text": "  ", "query": "q1"}, "q2", "q2"]},
            }
        },
    ]

    results, related = parse_web_cards(cards)
    assert len(results) == 1
    assert results[0].url == "https://mp.weixin.qq.com/s?x=1"
    assert results[0].source == "Account"
    assert results[0].date == "2026-11-12"
    assert results[0].snippet == "Snippet"
    assert related == ["q1", "q2"]


def test_web_cards_dedupe_normalizes_wechat_urls() -> None:
    cards = [
        {
            "data": {
                "cardName": "card-pc/card_normal_result",
                "vm": {
                    "title": "A",
                    "url": "https://mp.weixin.qq.com/s?x=1",
                    "content": "x",
                },
            }
        },
        {
            "data": {
                "cardName": "card-common/card30010608",
                "vm": {
                    "title": "A again",
                    "h5Url": "http://mp.weixin.qq.com/s?x=1",
                    "content": "x",
                },
            }
        },
    ]

    results, _ = parse_web_cards(cards)
    assert len(results) == 1


def test_hints_non_list_is_ignored() -> None:
    cards = [
        {
            "data": {
                "cardName": "card-pc/card_bottom_hint",
                "vm": {"hints": "not-a-list"},
            }
        }
    ]

    _, related = parse_web_cards(cards)
    assert related == []
