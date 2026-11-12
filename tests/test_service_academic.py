import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx

from yuanbao_search_mcp.client import UpstreamError
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
async def test_search_academic_empty_results_are_not_an_error(
    settings, academic_search_html
) -> None:
    respx.get(url__regex=r"https://so\.qq\.com/isearch\?.*tab=xueshu").mock(
        return_value=httpx.Response(200, text=academic_search_html)
    )
    respx.post("https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq").mock(
        return_value=httpx.Response(200, json={"data": {"sub_queries": []}})
    )
    respx.post("https://lizhiassistant.search.qq.com/academic_agent/frame_get").mock(
        return_value=httpx.Response(200, json={"data": {"sup_list": []}})
    )

    service = YuanbaoService(settings)
    try:
        result = await service.search_academic("大模型推理", limit=5)
        assert result.core_papers == []
        assert result.sub_questions == []
        assert any("returned no results" in warning for warning in result.warnings)
    finally:
        await service.aclose()


@respx.mock
async def test_search_academic_raises_when_both_calls_fail(
    settings, academic_search_html
) -> None:
    respx.get(url__regex=r"https://so\.qq\.com/isearch\?.*tab=xueshu").mock(
        return_value=httpx.Response(200, text=academic_search_html)
    )
    respx.post("https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq").mock(
        return_value=httpx.Response(500)
    )
    respx.post("https://lizhiassistant.search.qq.com/academic_agent/frame_get").mock(
        return_value=httpx.Response(500)
    )

    service = YuanbaoService(settings)
    try:
        with pytest.raises(UpstreamError):
            await service.search_academic("大模型推理", limit=5)
    finally:
        await service.aclose()


async def test_search_academic_cancellation_cleans_up(settings, monkeypatch) -> None:
    subq_started = asyncio.Event()
    subq_cancelled = asyncio.Event()

    class FakeSession:
        def __init__(self, client, query):
            pass

        async def create(self):
            return "sid"

        async def fetch_sup(self):
            await asyncio.sleep(10)

        async def fetch_sub_questions(self):
            subq_started.set()
            try:
                await asyncio.sleep(10)
            finally:
                subq_cancelled.set()

        async def fetch_summary(self, timeout):
            return ("", False, 0, False)

    monkeypatch.setattr("yuanbao_search_mcp.service.AcademicSession", FakeSession)

    service = YuanbaoService(settings)
    try:
        task = asyncio.create_task(
            service.search_academic("x", include_subquestions=True)
        )
        await asyncio.wait_for(subq_started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert subq_cancelled.is_set()
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
        assert any("summary" in warning.lower() for warning in result.warnings)
    finally:
        await service.aclose()
