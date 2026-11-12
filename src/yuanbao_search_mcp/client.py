"""HTTP client with rate limiting, retries, and TTL caching."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Generic, TypeVar

import httpx

from .config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class UpstreamError(RuntimeError):
    """Base class for upstream failures."""


class UpstreamBlockedError(UpstreamError):
    """Upstream returned a captcha or anti-crawl page."""


class UpstreamTimeoutError(UpstreamError):
    """Upstream request timed out."""


class UpstreamParseError(UpstreamError):
    """Upstream page or JSON could not be parsed."""


class ArticleUnavailableError(UpstreamError):
    """Article was deleted, restricted, or requires WeChat."""


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(0.0, min_interval)
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def wait(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            delay = self._next_at - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_at = time.monotonic() + self._min_interval


class TTLCache(Generic[T]):
    def __init__(self, ttl: float, maxsize: int = 256) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._data: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        if self._ttl <= 0:
            return None
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if time.monotonic() >= expires:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T) -> None:
        if self._ttl <= 0:
            return
        if len(self._data) >= self._maxsize:
            now = time.monotonic()
            self._data = {k: v for k, v in self._data.items() if v[0] > now}
            if len(self._data) >= self._maxsize:
                self._data.pop(next(iter(self._data)))
        self._data[key] = (time.monotonic() + self._ttl, value)


class HttpClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._limiter = RateLimiter(settings.min_interval)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout, connect=settings.connect_timeout),
            follow_redirects=True,
            proxy=settings.proxy,
            headers={
                "user-agent": settings.user_agent,
                "accept-language": "zh-CN,zh;q=0.9",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        rate_limit: bool = True,
        max_bytes: int = 15_000_000,
    ) -> str:
        if rate_limit:
            await self._limiter.wait()
        response = await self._request("GET", url, params=params, headers=headers)
        if len(response.content) > max_bytes:
            raise UpstreamError(f"Response from {url} is larger than {max_bytes} bytes")
        return response.text

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        rate_limit: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if rate_limit:
            await self._limiter.wait()
        kwargs: dict[str, Any] = {"json": payload, "headers": headers}
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = await self._request("POST", url, **kwargs)
        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamParseError(f"Invalid JSON from {url}") from exc
        if not isinstance(data, dict):
            raise UpstreamParseError(f"Unexpected JSON shape from {url}")
        return data

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                response = await self._client.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= self._settings.max_retries:
                    raise UpstreamTimeoutError(f"Request to {url} timed out") from exc
                await self._sleep_backoff(attempt)
                continue
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self._settings.max_retries:
                    raise UpstreamError(f"Request to {url} failed: {exc}") from exc
                await self._sleep_backoff(attempt)
                continue

            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt >= self._settings.max_retries:
                    raise UpstreamError(f"Upstream returned HTTP {response.status_code} for {url}")
                await self._sleep_backoff(attempt, response.headers.get("retry-after"))
                continue
            if response.status_code >= 400:
                raise UpstreamError(f"Upstream returned HTTP {response.status_code} for {url}")
            return response
        raise UpstreamError(f"Request to {url} failed") from last_error

    async def _sleep_backoff(self, attempt: int, retry_after: str | None = None) -> None:
        delay = 0.0
        if retry_after:
            try:
                delay = max(0.0, float(retry_after))
            except ValueError:
                delay = 0.0
        if delay <= 0:
            delay = min(8.0, 0.5 * (2**attempt))
        await asyncio.sleep(delay + random.uniform(0.0, 0.2))
