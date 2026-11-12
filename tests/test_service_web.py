import json

import httpx
import respx

from yuanbao_search_mcp.service import YuanbaoService


def rsc_html(cards: list[dict]) -> str:
    payload = json.dumps({"initialCards": cards}, ensure_ascii=False)
    chunk = json.dumps(payload, ensure_ascii=False)
    return f"<html><script>self.__next_f.push([1,{chunk}])</script></html>"


CARDS = [
    {
        "data": {
            "cardName": "card-pc/card_normal_result",
            "vm": {
                "title": "Result A",
                "url": "https://a.example.com",
                "sourcename": "Site A",
                "date": "2026-11-12",
                "content": "Snippet A",
            },
        }
    },
    {
        "data": {
            "cardName": "card-pc/card_bottom_hint",
            "vm": {"hints": [{"text": "related 1"}]},
        }
    },
]


@respx.mock
async def test_search_web(settings) -> None:
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=rsc_html(CARDS))
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_web("自进化", scope="all")
        assert result.count == 1
        assert result.results[0].title == "Result A"
        assert result.related_queries == ["related 1"]
        assert result.warnings == []
    finally:
        await service.aclose()


@respx.mock
async def test_search_web_date_filter_keeps_unknown(settings) -> None:
    from datetime import date

    today = date.today().isoformat()
    first = {
        "data": {
            "cardName": "card-pc/card_normal_result",
            "vm": {**CARDS[0]["data"]["vm"], "date": today},
        }
    }
    cards = [
        first,
        {
            "data": {
                "cardName": "card-pc/card_normal_result",
                "vm": {
                    "title": "Undated",
                    "url": "https://b.example.com",
                    "content": "No date",
                },
            }
        },
    ]
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=rsc_html(cards))
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_web("自进化", days=7)
        assert result.count == 2
        assert any(item.date_unknown for item in result.results)
        assert result.warnings
    finally:
        await service.aclose()
