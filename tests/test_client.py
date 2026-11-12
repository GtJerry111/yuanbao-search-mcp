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
    UpstreamParseError,
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


@respx.mock
async def test_post_json_invalid_json(settings) -> None:
    respx.post("https://example.com/api").mock(return_value=httpx.Response(200, text="not json"))
    client = HttpClient(settings)
    try:
        with pytest.raises(UpstreamParseError):
            await client.post_json("https://example.com/api", {"q": "x"})
    finally:
        await client.aclose()


@respx.mock
async def test_post_json_non_dict(settings) -> None:
    respx.post("https://example.com/api").mock(return_value=httpx.Response(200, json=["a"]))
    client = HttpClient(settings)
    try:
        with pytest.raises(UpstreamParseError):
            await client.post_json("https://example.com/api", {"q": "x"})
    finally:
        await client.aclose()


@respx.mock
async def test_retry_on_429(settings) -> None:
    settings = settings.model_copy(update={"max_retries": 1})
    route = respx.get("https://example.com/limited").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, text="ok"),
        ]
    )
    client = HttpClient(settings)
    try:
        assert await client.get("https://example.com/limited") == "ok"
        assert route.call_count == 2
    finally:
        await client.aclose()


@respx.mock
async def test_retry_exhaustion(settings) -> None:
    settings = settings.model_copy(update={"max_retries": 1})
    route = respx.get("https://example.com/down").mock(return_value=httpx.Response(500))
    client = HttpClient(settings)
    try:
        with pytest.raises(UpstreamError):
            await client.get("https://example.com/down")
        assert route.call_count == 2
    finally:
        await client.aclose()


@respx.mock
async def test_max_bytes_rejects(settings) -> None:
    respx.get("https://example.com/big").mock(return_value=httpx.Response(200, text="x" * 100))
    client = HttpClient(settings)
    try:
        with pytest.raises(UpstreamError):
            await client.get("https://example.com/big", max_bytes=10)
    finally:
        await client.aclose()


def test_cache_evicts_oldest() -> None:
    cache: TTLCache[str] = TTLCache(ttl=60, maxsize=2)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")
    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") == "3"


def test_cache_zero_maxsize_is_safe() -> None:
    cache: TTLCache[str] = TTLCache(ttl=60, maxsize=0)
    cache.set("a", "v")
    assert cache.get("a") is None


async def test_rate_limiter_disabled_is_fast() -> None:
    limiter = RateLimiter(0)
    loop = asyncio.get_running_loop()
    start = loop.time()
    await limiter.wait()
    await limiter.wait()
    assert loop.time() - start < 0.05


async def test_empty_proxy_is_accepted(settings) -> None:
    settings = settings.model_copy(update={"proxy": ""})
    client = HttpClient(settings)
    await client.aclose()
