from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from yuanbao_search_mcp.client import (
    HttpClient,
    RateLimiter,
    TTLCache,
    UpstreamError,
    UpstreamTimeoutError,
)


def test_ttl_cache_expires() -> None:
    cache: TTLCache[str] = TTLCache(ttl=0.01)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    import time

    time.sleep(0.02)
    assert cache.get("k") is None


def test_ttl_cache_disabled() -> None:
    cache: TTLCache[str] = TTLCache(ttl=0)
    cache.set("k", "v")
    assert cache.get("k") is None


async def test_rate_limiter_waits() -> None:
    limiter = RateLimiter(0.05)
    start = asyncio.get_running_loop().time()
    await limiter.wait()
    await limiter.wait()
    elapsed = asyncio.get_running_loop().time() - start
    assert elapsed >= 0.045


@respx.mock
async def test_retries_on_500(settings) -> None:
    settings = settings.model_copy(update={"max_retries": 1})
    route = respx.get("https://example.com/x").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, text="ok")]
    )
    client = HttpClient(settings)
    try:
        assert await client.get("https://example.com/x") == "ok"
        assert route.call_count == 2
    finally:
        await client.aclose()


async def test_timeout_raises(settings) -> None:
    settings = settings.model_copy(update={"max_retries": 0, "request_timeout": 0.01})
    with respx.mock:
        respx.get("https://example.com/slow").mock(side_effect=httpx.ReadTimeout("slow"))
        client = HttpClient(settings)
        try:
            with pytest.raises(UpstreamTimeoutError):
                await client.get("https://example.com/slow")
        finally:
            await client.aclose()


async def test_404_raises_without_retry(settings) -> None:
    settings = settings.model_copy(update={"max_retries": 2})
    with respx.mock:
        route = respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))
        client = HttpClient(settings)
        try:
            with pytest.raises(UpstreamError):
                await client.get("https://example.com/missing")
            assert route.call_count == 1
        finally:
            await client.aclose()
