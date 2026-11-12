import json
from pathlib import Path

import httpx
import respx

from yuanbao_search_mcp.service import YuanbaoService

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@respx.mock
async def test_search_academic(settings, academic_search_html) -> None:
    subq = _load("academic_subq.json")
    sup = _load("academic_sup.json")

    respx.get(url__regex=r"https://so\.qq\.com/isearch\?.*tab=xueshu").mock(
        return_value=httpx.Response(200, text=academic_search_html)
    )
    respx.post("https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq").mock(
        return_value=httpx.Response(200, json=subq)
    )

    def frame_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("get_sup"):
            return httpx.Response(200, json=sup)
        return httpx.Response(
            200,
            json={
                "data": {
                    "steps": [{"step_text": "Summary text."}],
                    "next_frame_id": -1,
                    "finish_reason": "stop",
                }
            },
        )

    respx.post("https://lizhiassistant.search.qq.com/academic_agent/frame_get").mock(
        side_effect=frame_handler
    )

    service = YuanbaoService(settings)
    try:
        result = await service.search_academic(
            "大模型推理", limit=5, include_summary=True, summary_timeout=5
        )
        assert len(result.core_papers) == 5
        assert len(result.sub_questions) == 8
        assert result.summary == "Summary text."
        assert result.summary_truncated is False
        assert result.warnings == []
    finally:
        await service.aclose()


@respx.mock
async def test_search_academic_partial_when_sup_fails(settings, academic_search_html) -> None:
    subq = _load("academic_subq.json")

    respx.get(url__regex=r"https://so\.qq\.com/isearch\?.*tab=xueshu").mock(
        return_value=httpx.Response(200, text=academic_search_html)
    )
    respx.post("https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq").mock(
        return_value=httpx.Response(200, json=subq)
    )
    respx.post("https://lizhiassistant.search.qq.com/academic_agent/frame_get").mock(
        return_value=httpx.Response(500)
    )

    service = YuanbaoService(settings)
    try:
        result = await service.search_academic("大模型推理", limit=5)
        assert result.core_papers == []
        assert len(result.sub_questions) == 8
        assert result.warnings
    finally:
        await service.aclose()


@respx.mock
async def test_search_academic_summary_timeout(settings, academic_search_html) -> None:
    subq = _load("academic_subq.json")
    sup = _load("academic_sup.json")

    respx.get(url__regex=r"https://so\.qq\.com/isearch\?.*tab=xueshu").mock(
        return_value=httpx.Response(200, text=academic_search_html)
    )
    respx.post("https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq").mock(
        return_value=httpx.Response(200, json=subq)
    )

    def frame_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("get_sup"):
            return httpx.Response(200, json=sup)
        return httpx.Response(
            200,
            json={
                "data": {
                    "steps": [{"step_text": "Partial."}],
                    "next_frame_id": 1,
                    "finish_reason": "",
                }
            },
        )

    respx.post("https://lizhiassistant.search.qq.com/academic_agent/frame_get").mock(
        side_effect=frame_handler
    )

    service = YuanbaoService(settings)
    try:
        result = await service.search_academic(
            "大模型推理", limit=5, include_summary=True, summary_timeout=0.3
        )
        assert result.summary
        assert result.summary_truncated is True
    finally:
        await service.aclose()
