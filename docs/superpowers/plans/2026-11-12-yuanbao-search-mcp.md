# Yuanbao Search MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standard MCP server that exposes Tencent Yuanbao's pure-HTTP capabilities — WeChat official-account article search, article reading, academic search, and general web search — to any MCP client.

**Architecture:** A Python package with four tool handlers backed by a shared `YuanbaoService`. The service uses one `httpx` client with rate limiting, retries, and in-memory TTL caches. A parser layer turns `so.qq.com`'s React Server Components payload into structured models; a second layer calls the academic session APIs and normalizes papers/summaries. MCP tools return Pydantic models as structured JSON. Transport is stdio by default, with optional Streamable HTTP.

**Tech Stack:** Python 3.11+, `mcp>=2,<3` (`MCPServer`), `httpx`, `beautifulsoup4` + `lxml`, `pydantic` + `pydantic-settings`, `pytest` + `pytest-asyncio` + `respx`, `ruff`, `uv`.

**Design references:**
- `DESIGN.md` — agreed design decisions.
- `CAPABILITIES.md` — upstream capability investigation.

---

## File map

| File | Responsibility |
|---|---|
| `src/yuanbao_search_mcp/__init__.py` | Version |
| `src/yuanbao_search_mcp/__main__.py` | `python -m yuanbao_search_mcp` entry point |
| `src/yuanbao_search_mcp/config.py` | `Settings`, env parsing, CLI overrides |
| `src/yuanbao_search_mcp/models.py` | Pydantic input/output models |
| `src/yuanbao_search_mcp/client.py` | `HttpClient`, rate limiter, TTL cache, retries, errors |
| `src/yuanbao_search_mcp/parsers.py` | RSC payload, WeChat cards, article HTML, web cards, dates |
| `src/yuanbao_search_mcp/academic.py` | Academic session, sub-question/sup/summary parsing |
| `src/yuanbao_search_mcp/service.py` | Four high-level operations |
| `src/yuanbao_search_mcp/server.py` | `MCPServer`, tool registration, CLI |
| `scripts/smoke_test.py` | Live end-to-end smoke test |
| `tests/fixtures/` | Recorded upstream HTML/JSON fixtures |
| `tests/test_*.py` | Unit, mock-HTTP, and protocol tests |

---

## Task 1: Scaffolding and repository hygiene

**Files:**
- Create: `.gitignore`, `LICENSE`, `README.md`, `README.zh-CN.md`
- Create: `src/yuanbao_search_mcp/__main__.py`
- Modify: `pyproject.toml`, `src/yuanbao_search_mcp/__init__.py`
- Test: `tests/test_package.py`

- [ ] **Step 1: Write `.gitignore`**

```text
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.env
.superpowers/
dist/
build/
*.egg-info/
.DS_Store
```

- [ ] **Step 2: Pin MCP v2 and Python 3.11+ in `pyproject.toml`**

Change the dependency and Python floor:

```toml
requires-python = ">=3.11"

dependencies = [
    "mcp>=2,<3",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "lxml>=5.2",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]
```

Then refresh the lockfile:

```bash
uv sync
```

Expected: `mcp` resolves to a `2.x` version. Verify:

```bash
uv run python -c "import importlib.metadata as m; print(m.version('mcp'))"
```

- [ ] **Step 3: Write `LICENSE`**

Use the standard MIT license text with:

```text
Copyright (c) 2026 Jerry
```

- [ ] **Step 4: Write the bilingual README stubs**

`README.md`:

```markdown
# yuanbao-search-mcp

[English](README.md) | [简体中文](README.zh-CN.md)

MCP server for Tencent Yuanbao Search: WeChat official-account articles,
academic search, and general web search.

> Personal-use project. Not affiliated with Tencent. See the full documentation
> below for limitations and compliance notes.
```

`README.zh-CN.md`:

```markdown
# yuanbao-search-mcp

[English](README.md) | [简体中文](README.zh-CN.md)

腾讯元宝搜索 MCP：公众号文章搜索、学术搜索、通用网页搜索。

> 个人使用项目，与腾讯无关。完整的能力边界和合规说明见下文。
```

- [ ] **Step 5: Write `src/yuanbao_search_mcp/__init__.py`**

```python
"""MCP server for Tencent Yuanbao search."""

__version__ = "0.1.0"
```

- [ ] **Step 6: Write `src/yuanbao_search_mcp/__main__.py`**

```python
from .server import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Write `tests/test_package.py`**

```python
import yuanbao_search_mcp


def test_version_is_exposed() -> None:
    assert yuanbao_search_mcp.__version__ == "0.1.0"
```

- [ ] **Step 8: Verify the package imports**

Run:

```bash
cd ~/Projects/yuanbao-search-mcp
uv run python -c "import yuanbao_search_mcp; print(yuanbao_search_mcp.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 9: Initialize git and commit**

```bash
git init
git add .gitignore LICENSE README.md README.zh-CN.md pyproject.toml uv.lock \
  CAPABILITIES.md DESIGN.md docs src tests
git commit -m "chore: scaffold yuanbao-search-mcp"
```

---

## Task 2: Pydantic models

**Files:**
- Create: `src/yuanbao_search_mcp/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:

```python
from yuanbao_search_mcp.models import (
    AcademicPaper,
    ArticleResult,
    WeixinArticle,
    WeixinSearchResult,
    WebResult,
    WebSearchResult,
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
    result = WebSearchResult(query="q", scope="all", count=1, results=[WebResult(title="T", url="https://x")])
    assert result.results[0].date_unknown is False
    assert result.related_queries == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'yuanbao_search_mcp.models'` or an import error.

- [ ] **Step 3: Write `src/yuanbao_search_mcp/models.py`**

```python
"""Pydantic models returned by MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WeixinArticle(BaseModel):
    title: str
    account: str | None = None
    publish_time: str | None = None
    summary: str | None = None
    url: str
    doc_id: str | None = None
    cover_url: str | None = None
    date_unknown: bool = False


class WeixinSearchResult(BaseModel):
    query: str
    account: str | None = None
    count: int
    total_available: int
    results: list[WeixinArticle] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ArticleResult(BaseModel):
    title: str
    account: str | None = None
    publish_time: str | None = None
    url: str
    content: str
    char_count: int
    original_chars: int
    truncated: bool
    images: list[str] = Field(default_factory=list)
    image_count: int = 0


class AcademicEvidence(BaseModel):
    quote_number: int
    quote: str


class AcademicPaper(BaseModel):
    citation_id: int | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    venue: str | None = None
    year: str | None = None
    cited_by: int | None = None
    url: str | None = None
    abstract: str | None = None
    abstract_truncated: bool = False
    evidence: list[AcademicEvidence] = Field(default_factory=list)


class AcademicDoc(BaseModel):
    title: str
    venue: str | None = None
    year: str | None = None
    url: str | None = None
    abstract_short: str | None = None


class AcademicSubQuestion(BaseModel):
    question: str
    papers: list[AcademicDoc] = Field(default_factory=list)


class AcademicSearchResult(BaseModel):
    query: str
    core_papers: list[AcademicPaper] = Field(default_factory=list)
    sub_questions: list[AcademicSubQuestion] = Field(default_factory=list)
    summary: str | None = None
    summary_truncated: bool = False
    summary_char_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class WebResult(BaseModel):
    title: str
    url: str
    source: str | None = None
    date: str | None = None
    snippet: str | None = None
    date_unknown: bool = False


class WebSearchResult(BaseModel):
    query: str
    scope: Literal["all", "gov", "media"]
    count: int
    results: list[WebResult] = Field(default_factory=list)
    related_queries: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_models.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/models.py tests/test_models.py
git commit -m "feat: add pydantic output models"
```

---

## Task 3: Configuration

**Files:**
- Create: `src/yuanbao_search_mcp/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
from yuanbao_search_mcp.config import Settings, load_settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.transport == "stdio"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.weixin_default_limit == 20
    assert settings.weixin_max_results == 28
    assert settings.academic_summary_default is False
    assert settings.academic_summary_timeout == 45.0
    assert settings.enable_weixin_search is True


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("YUANBAO_TRANSPORT", "streamable-http")
    monkeypatch.setenv("YUANBAO_PORT", "9999")
    monkeypatch.setenv("YUANBAO_ACADEMIC_SUMMARY_DEFAULT", "true")
    monkeypatch.setenv("YUANBAO_ENABLE_WEB_SEARCH", "false")
    settings = Settings(_env_file=None)
    assert settings.transport == "streamable-http"
    assert settings.port == 9999
    assert settings.academic_summary_default is True
    assert settings.enable_web_search is False


def test_cli_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("YUANBAO_PORT", "9999")
    settings = load_settings(["--port", "8765", "--transport", "stdio"])
    assert settings.port == 8765
    assert settings.transport == "stdio"


def test_invalid_port_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        Settings(_env_file=None, port=70000)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError` for `config`.

- [ ] **Step 3: Write `src/yuanbao_search_mcp/config.py`**

```python
"""Configuration for the Yuanbao Search MCP server."""

from __future__ import annotations

import argparse
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
WECHAT_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.47"
)


class Settings(BaseSettings):
    """Runtime settings, loaded from YUANBAO_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="YUANBAO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    server_name: str = "yuanbao_search_mcp"
    version: str = "0.1.0"
    transport: Literal["stdio", "streamable-http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    log_level: str = "INFO"

    enable_weixin_search: bool = True
    enable_article_reader: bool = True
    enable_academic_search: bool = True
    enable_web_search: bool = True

    weixin_default_limit: int = Field(default=20, ge=1, le=28)
    weixin_max_results: int = Field(default=28, ge=1, le=28)
    web_default_limit: int = Field(default=10, ge=1, le=20)
    web_max_results: int = Field(default=20, ge=1, le=20)
    academic_default_limit: int = Field(default=10, ge=1, le=20)
    academic_max_papers: int = Field(default=20, ge=1, le=20)
    academic_summary_default: bool = False
    academic_summary_timeout: float = Field(default=45.0, ge=5, le=120)
    article_max_chars: int = Field(default=20000, ge=1000, le=100000)

    request_timeout: float = Field(default=20.0, ge=5, le=120)
    connect_timeout: float = Field(default=10.0, ge=1, le=60)
    max_retries: int = Field(default=2, ge=0, le=5)
    min_interval: float = Field(default=1.0, ge=0, le=60)
    cache_ttl: float = Field(default=300.0, ge=0)
    article_cache_ttl: float = Field(default=1800.0, ge=0)
    academic_cache_ttl: float = Field(default=600.0, ge=0)
    proxy: str | None = None
    user_agent: str = DEFAULT_USER_AGENT

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yuanbao-search-mcp",
        description="MCP server for Tencent Yuanbao search.",
    )
    parser.add_argument("--transport", choices=["stdio", "streamable-http"])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--log-level")
    parser.add_argument("--version", action="version", version="yuanbao-search-mcp 0.1.0")
    return parser.parse_args(argv)


def load_settings(argv: list[str] | None = None) -> Settings:
    args = parse_args(argv)
    settings = Settings()
    updates: dict[str, object] = {}
    if args.transport:
        updates["transport"] = args.transport
    if args.host:
        updates["host"] = args.host
    if args.port is not None:
        updates["port"] = args.port
    if args.log_level:
        updates["log_level"] = args.log_level
    return settings.model_copy(update=updates) if updates else settings
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/config.py tests/test_config.py
git commit -m "feat: add environment and CLI configuration"
```

---

## Task 4: HTTP client, rate limiter, cache, retries

**Files:**
- Create: `src/yuanbao_search_mcp/client.py`
- Test: `tests/conftest.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from yuanbao_search_mcp.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        _env_file=None,
        min_interval=0.0,
        cache_ttl=0.0,
        article_cache_ttl=0.0,
        academic_cache_ttl=0.0,
        max_retries=0,
        request_timeout=5.0,
    )


@pytest.fixture()
def weixin_search_html() -> str:
    return (FIXTURES / "weixin_search.html").read_text(encoding="utf-8")


@pytest.fixture()
def academic_search_html() -> str:
    return (FIXTURES / "academic_search.html").read_text(encoding="utf-8")
```

- [ ] **Step 2: Write the failing tests**

`tests/test_client.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
uv run pytest tests/test_client.py -v
```

Expected: `ModuleNotFoundError` for `client`.

- [ ] **Step 4: Write `src/yuanbao_search_mcp/client.py`**

```python
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
                    raise UpstreamError(
                        f"Upstream returned HTTP {response.status_code} for {url}"
                    )
                await self._sleep_backoff(attempt, response.headers.get("retry-after"))
                continue
            if response.status_code >= 400:
                raise UpstreamError(
                    f"Upstream returned HTTP {response.status_code} for {url}"
                )
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
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_client.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/yuanbao_search_mcp/client.py tests/conftest.py tests/test_client.py
git commit -m "feat: add http client with rate limit, cache, and retries"
```

---

## Task 5: RSC payload and WeChat card parsers

**Files:**
- Create: `src/yuanbao_search_mcp/parsers.py`
- Test: `tests/test_parsers_weixin.py`

- [ ] **Step 1: Write the failing test**

`tests/test_parsers_weixin.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_parsers_weixin.py -v
```

Expected: `ModuleNotFoundError` for `parsers`.

- [ ] **Step 3: Write the first half of `src/yuanbao_search_mcp/parsers.py`**

```python
"""Parsers for Yuanbao search result pages and WeChat article pages."""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from .client import ArticleUnavailableError, UpstreamParseError
from .models import WeixinArticle, WebResult

_HIGHLIGHT_RE = re.compile(r"[\ue40a\ue40b]")
_TAG_RE = re.compile(r"<[^>]+>")
_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', re.S)
_DATE_RE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
_DATE_CN_RE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日")
_FIGURE_RE = re.compile(r"<figure\b[^>]*>.*?</figure>", re.S | re.I)

_BLOCK_MARKERS = (
    "环境异常",
    "请输入验证码",
    "访问过于频繁",
    "操作频繁",
    "请在微信客户端打开链接",
)
_ARTICLE_ERROR_MARKERS = (
    "该内容已被发布者删除",
    "此内容因违规无法查看",
    "内容已被删除",
    "参数错误",
)


@dataclass
class ParsedArticle:
    title: str
    account: str | None
    publish_time: str | None
    content: str
    images: list[str] = field(default_factory=list)


def strip_highlight(value: str) -> str:
    return _HIGHLIGHT_RE.sub("", value)


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = html_lib.unescape(value)
    text = _TAG_RE.sub("", text)
    text = strip_highlight(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def truncate(text: str | None, limit: int) -> tuple[str | None, bool]:
    if text is None:
        return None, False
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip(), True


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname == "mp.weixin.qq.com" and parsed.scheme == "http":
        return "https://" + url[len("http://") :]
    return url


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    match = _DATE_RE.search(text) or _DATE_CN_RE.search(text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def extract_year(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:19|20)\d{2}", value)
    return match.group(0) if match else None


def extract_next_payload(html: str) -> str:
    chunks = _CHUNK_RE.findall(html)
    if not chunks:
        return html
    parts: list[str] = []
    for chunk in chunks:
        try:
            parts.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _extract_json_object(text: str, start: int) -> dict[str, Any]:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise UpstreamParseError("Unbalanced JSON object in RSC payload")


def extract_initial_cards(html: str) -> list[dict[str, Any]]:
    payload = extract_next_payload(html)
    marker = '{"initialCards":'
    start = payload.find(marker)
    if start < 0:
        marker = '\\"initialCards\\":'
        start = payload.find(marker)
        if start < 0:
            return []
        payload = payload.replace('\\"', '"').replace("\\\\", "\\")
        start = payload.find('{"initialCards":')
        if start < 0:
            return []
    try:
        data = _extract_json_object(payload, start)
    except (json.JSONDecodeError, UpstreamParseError):
        return []
    cards = data.get("initialCards")
    return cards if isinstance(cards, list) else []


def parse_weixin_cards(cards: list[dict[str, Any]]) -> list[WeixinArticle]:
    results: list[WeixinArticle] = []
    seen: set[str] = set()
    for card in cards:
        data = card.get("data") or {}
        vm = data.get("vm") or {}
        if data.get("cardName") != "card-common/card30010612" and not vm.get("isWxmpTab"):
            continue
        title = clean_text(vm.get("title"))
        raw_url = vm.get("jumpUrl")
        if not title or not isinstance(raw_url, str) or not raw_url:
            continue
        url = normalize_url(raw_url)
        doc_id = str(vm.get("docId") or "") or None
        key = doc_id or url
        if key in seen:
            continue
        seen.add(key)
        results.append(
            WeixinArticle(
                title=title,
                account=clean_text(vm.get("authorName")),
                publish_time=clean_text(vm.get("publishTime")),
                summary=clean_text(vm.get("summary")),
                url=url,
                doc_id=doc_id,
                cover_url=vm.get("imgUrl") if isinstance(vm.get("imgUrl"), str) else None,
                date_unknown=parse_date(clean_text(vm.get("publishTime"))) is None,
            )
        )
    return results


def is_blocked_page(html: str) -> bool:
    return any(marker in html for marker in _BLOCK_MARKERS)


def is_article_error_page(html: str) -> bool:
    return any(marker in html for marker in _ARTICLE_ERROR_MARKERS)
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_parsers_weixin.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/parsers.py tests/test_parsers_weixin.py
git commit -m "feat: parse rsc payload and weixin result cards"
```

---

## Task 6: WeChat article parser

**Files:**
- Modify: `src/yuanbao_search_mcp/parsers.py`
- Test: `tests/test_parsers_article.py`

- [ ] **Step 1: Write the failing test**

`tests/test_parsers_article.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/test_parsers_article.py -v
```

Expected: `ImportError: cannot import name 'parse_weixin_article'`.

- [ ] **Step 3: Append the article parser to `src/yuanbao_search_mcp/parsers.py`**

```python
def _select_text(soup: BeautifulSoup, selector: str) -> str | None:
    node = soup.select_one(selector)
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def _meta_content(soup: BeautifulSoup, key: str) -> str | None:
    for attr in ("property", "name"):
        node = soup.select_one(f'meta[{attr}="{key}"]')
        if node and node.get("content"):
            return str(node["content"]).strip() or None
    return None


def extract_images(node: Tag) -> list[str]:
    images: list[str] = []
    for img in node.select("img"):
        src = img.get("data-src") or img.get("src") or ""
        if not isinstance(src, str) or not src.startswith("http"):
            continue
        if "mmbiz.qpic.cn" not in src:
            continue
        src = html_lib.unescape(src)
        if src not in images:
            images.append(src)
    return images


def html_to_markdown(node: Tag) -> str:
    for tag in node.select("script, style, noscript, svg, iframe"):
        tag.decompose()
    for br in node.find_all("br"):
        br.replace_with("\n")
    for level in range(1, 7):
        for heading in node.find_all(f"h{level}"):
            heading.insert(0, f"{'#' * level} ")
            heading.append("\n")
    for item in node.find_all("li"):
        item.insert(0, "- ")
        item.append("\n")
    for quote in node.find_all("blockquote"):
        quote.insert(0, "> ")
        quote.append("\n")
    for block in node.find_all(["p", "section", "div"]):
        block.append("\n")
    text = node.get_text("")
    text = "\n".join(line.strip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_weixin_article(html: str) -> ParsedArticle:
    soup = BeautifulSoup(html, "lxml")
    content_node = soup.select_one("#js_content")
    if content_node is None:
        if is_article_error_page(html) or is_blocked_page(html):
            raise ArticleUnavailableError(
                "Article is deleted, restricted, or requires the WeChat client."
            )
        raise UpstreamParseError("Article content node #js_content was not found")

    title = _select_text(soup, "#activity-name") or _meta_content(soup, "og:title")
    if not title:
        raise UpstreamParseError("Article title was not found")

    return ParsedArticle(
        title=title,
        account=_select_text(soup, "#js_name") or _meta_content(soup, "author"),
        publish_time=_select_text(soup, "#publish_time")
        or _meta_content(soup, "article:published_time"),
        content=html_to_markdown(content_node),
        images=extract_images(content_node),
    )
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_parsers_article.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/parsers.py tests/test_parsers_article.py
git commit -m "feat: parse weixin article html into markdown"
```

---

## Task 7: Web result parser

**Files:**
- Modify: `src/yuanbao_search_mcp/parsers.py`
- Test: `tests/test_parsers_web.py`

- [ ] **Step 1: Write the failing test**

`tests/test_parsers_web.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/test_parsers_web.py -v
```

Expected: `ImportError: cannot import name 'parse_web_cards'`.

- [ ] **Step 3: Append the web parser to `src/yuanbao_search_mcp/parsers.py`**

```python
def _web_card_result(vm: dict[str, Any]) -> WebResult | None:
    title = clean_text(vm.get("title"))
    url = vm.get("url") or vm.get("h5Url")
    if not title or not isinstance(url, str) or not url:
        return None
    raw_date = clean_text(vm.get("date")) or clean_text(vm.get("publishTime"))
    return WebResult(
        title=title,
        url=url,
        source=clean_text(vm.get("sourcename")) or clean_text(vm.get("showname")),
        date=raw_date,
        snippet=clean_text(vm.get("content")),
        date_unknown=parse_date(raw_date) is None,
    )


def parse_web_cards(cards: list[dict[str, Any]]) -> tuple[list[WebResult], list[str]]:
    results: list[WebResult] = []
    related: list[str] = []
    seen_urls: set[str] = set()

    for card in cards:
        data = card.get("data") or {}
        vm = data.get("vm") or {}
        name = data.get("cardName") or ""

        if name in ("card-pc/card_normal_result", "card-pc/card30010588", "card-common/card30010608"):
            item = _web_card_result(vm)
            if item and item.url not in seen_urls:
                seen_urls.add(item.url)
                results.append(item)
            continue

        if name in ("card-pc/card_bottom_hint", "card-pc/card_hint_middle"):
            for hint in vm.get("hints") or []:
                if isinstance(hint, dict):
                    text = clean_text(hint.get("text") or hint.get("query"))
                else:
                    text = clean_text(hint)
                if text and text not in related:
                    related.append(text)

    return results, related
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_parsers_web.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/parsers.py tests/test_parsers_web.py
git commit -m "feat: parse general web result cards"
```

---

## Task 8: Academic parsing and session

**Files:**
- Create: `src/yuanbao_search_mcp/academic.py`
- Test: `tests/test_academic.py`

- [ ] **Step 1: Write the failing test**

`tests/test_academic.py`:

```python
import json
from pathlib import Path

from yuanbao_search_mcp.academic import (
    extract_session_id,
    parse_sub_questions,
    parse_summary_frame,
    parse_sup,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_session_id() -> None:
    html = (FIXTURES / "academic_search.html").read_text(encoding="utf-8")
    session_id = extract_session_id(html)
    assert len(session_id) == 36
    assert session_id.count("-") == 4


def test_parse_sup() -> None:
    payload = json.loads((FIXTURES / "academic_sup.json").read_text(encoding="utf-8"))
    papers = parse_sup(payload)
    assert len(papers) == 18
    assert papers[0].citation_id == 1
    assert papers[0].title
    assert papers[0].authors
    assert papers[0].year
    assert len(papers[0].evidence) == 2


def test_parse_sub_questions() -> None:
    payload = json.loads((FIXTURES / "academic_subq.json").read_text(encoding="utf-8"))
    sub_questions = parse_sub_questions(payload)
    assert len(sub_questions) == 8
    assert all(len(question.papers) == 4 for question in sub_questions)
    assert sub_questions[0].question
    assert sub_questions[0].papers[0].title


def test_parse_summary_frame() -> None:
    payload = {
        "data": {
            "steps": [{"step_text": "Part one."}],
            "next_frame_id": 1,
            "finish_reason": "",
            "figures": [],
        }
    }
    text, next_frame, finished = parse_summary_frame(payload)
    assert text == "Part one."
    assert next_frame == 1
    assert finished is False

    final = {
        "data": {
            "steps": [{"step_text": "Part two."}],
            "next_frame_id": -1,
            "finish_reason": "stop",
        }
    }
    text, next_frame, finished = parse_summary_frame(final)
    assert text == "Part two."
    assert finished is True
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_academic.py -v
```

Expected: `ModuleNotFoundError` for `academic`.

- [ ] **Step 3: Write `src/yuanbao_search_mcp/academic.py`**

```python
"""Academic search session and response parsing."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import quote

from .client import (
    HttpClient,
    UpstreamBlockedError,
    UpstreamError,
    UpstreamParseError,
    UpstreamTimeoutError,
)
from .models import AcademicDoc, AcademicEvidence, AcademicPaper, AcademicSubQuestion
from .parsers import (
    _FIGURE_RE,
    clean_text,
    extract_year,
    is_blocked_page,
    truncate,
)

_SESSION_RE = re.compile(r'sessionId\\?"\s*:\s*\\?"([0-9a-f-]{36})', re.I)
_UUID_RE = re.compile(r'uuid\\?"\s*:\s*\\?"([0-9a-f-]{36})', re.I)

ACADEMIC_PAGE = "https://so.qq.com/isearch"
SUBQ_URL = "https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq"
FRAME_URL = "https://lizhiassistant.search.qq.com/academic_agent/frame_get"


def extract_session_id(html: str) -> str:
    match = _SESSION_RE.search(html) or _UUID_RE.search(html)
    if not match:
        raise UpstreamParseError("Could not create an academic session")
    return match.group(1)


def _check_payload(payload: dict[str, Any]) -> None:
    code = payload.get("code")
    if code not in (None, 0):
        raise UpstreamError(f"Academic API error {code}: {payload.get('msg') or 'unknown'}")
    status = payload.get("status")
    if isinstance(status, dict) and status.get("code") not in (None, 0):
        raise UpstreamError(
            f"Academic API error {status.get('code')}: {status.get('msg') or 'unknown'}"
        )


def parse_sup(payload: dict[str, Any]) -> list[AcademicPaper]:
    items = ((payload.get("data") or {}).get("sup_list")) or []
    papers: list[AcademicPaper] = []
    seen: set[str] = set()
    for item in items:
        title = clean_text(item.get("title"))
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        authors = item.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        authors = [author for author in (clean_text(value) for value in authors) if author]

        evidence: list[AcademicEvidence] = []
        for entry in (item.get("evidences") or [])[:2]:
            quote = clean_text(entry.get("quote"))
            if not quote:
                continue
            evidence.append(
                AcademicEvidence(
                    quote_number=int(entry.get("quote_number") or len(evidence) + 1),
                    quote=truncate(quote, 300)[0] or "",
                )
            )

        abstract, abstract_truncated = truncate(clean_text(item.get("abstract")), 1200)
        papers.append(
            AcademicPaper(
                citation_id=int(item["id"]) if item.get("id") is not None else None,
                title=title,
                authors=authors,
                venue=clean_text(item.get("journal_name")),
                year=extract_year(item.get("publication_date")),
                cited_by=int(item["cited_by_count"])
                if item.get("cited_by_count") is not None
                else None,
                url=item.get("url") if isinstance(item.get("url"), str) else None,
                abstract=abstract,
                abstract_truncated=abstract_truncated,
                evidence=evidence,
            )
        )
    return papers


def parse_sub_questions(payload: dict[str, Any]) -> list[AcademicSubQuestion]:
    items = ((payload.get("data") or {}).get("sub_queries")) or []
    result: list[AcademicSubQuestion] = []
    for item in items:
        question = clean_text(item.get("display_title") or item.get("query"))
        if not question:
            continue
        papers: list[AcademicDoc] = []
        seen: set[str] = set()
        for doc in item.get("docs") or []:
            title = clean_text(doc.get("title"))
            url = doc.get("url")
            if not title or not isinstance(url, str) or not url:
                continue
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            abstract, _ = truncate(
                clean_text(doc.get("abstract_short") or doc.get("abstract")), 300
            )
            papers.append(
                AcademicDoc(
                    title=title,
                    venue=clean_text(doc.get("journal_name")) or clean_text(doc.get("show_name")),
                    year=str(doc["year"])
                    if doc.get("year") is not None
                    else extract_year(doc.get("publication_date")),
                    url=url,
                    abstract_short=abstract,
                )
            )
        result.append(AcademicSubQuestion(question=question, papers=papers[:4]))
    return result


def parse_summary_frame(payload: dict[str, Any]) -> tuple[str, int | None, bool]:
    data = payload.get("data") or {}
    steps = data.get("steps") or []
    text = "\n".join(
        step.get("step_text", "")
        for step in steps
        if isinstance(step, dict) and step.get("step_text")
    )
    next_frame = data.get("next_frame_id")
    if not isinstance(next_frame, int):
        next_frame = None
    finished = bool(data.get("finish_reason")) or next_frame is None or next_frame <= 0
    return text, next_frame, finished


class AcademicSession:
    def __init__(self, client: HttpClient, query: str) -> None:
        self._client = client
        self.query = query
        self.session_id = ""
        self.page_url = f"{ACADEMIC_PAGE}?query={quote(query)}&tab=xueshu"

    def _headers(self) -> dict[str, str]:
        return {
            "origin": "https://so.qq.com",
            "referer": self.page_url,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
        }

    async def create(self) -> str:
        html = await self._client.get(
            ACADEMIC_PAGE,
            params={"query": self.query, "tab": "xueshu"},
        )
        if is_blocked_page(html):
            raise UpstreamBlockedError("Yuanbao returned an anti-crawl page")
        self.session_id = extract_session_id(html)
        return self.session_id

    async def fetch_sub_questions(self) -> list[AcademicSubQuestion]:
        payload = await self._client.post_json(
            SUBQ_URL,
            {
                "query": self.query,
                "uuid": self.session_id,
                "guid": "",
                "session_id": self.session_id,
            },
            headers=self._headers(),
        )
        _check_payload(payload)
        return parse_sub_questions(payload)

    async def fetch_sup(self) -> list[AcademicPaper]:
        payload = await self._client.post_json(
            FRAME_URL,
            {"session_id": self.session_id, "get_sup": 1, "pass_through": ""},
            headers=self._headers(),
            timeout=60.0,
        )
        _check_payload(payload)
        return parse_sup(payload)

    async def fetch_summary(
        self,
        timeout: float,
        poll_interval: float = 0.1,
    ) -> tuple[str, bool, int, bool]:
        deadline = time.monotonic() + timeout
        frame = 0
        chunks: list[str] = []
        truncated = False
        figures_omitted = False

        while time.monotonic() < deadline:
            remaining = max(0.5, deadline - time.monotonic())
            try:
                payload = await self._client.post_json(
                    FRAME_URL,
                    {"session_id": self.session_id, "frame_id": frame, "pass_through": ""},
                    headers=self._headers(),
                    rate_limit=False,
                    timeout=min(remaining, 30.0),
                )
            except UpstreamTimeoutError:
                truncated = True
                break
            except UpstreamError:
                truncated = True
                break

            _check_payload(payload)
            text, next_frame, finished = parse_summary_frame(payload)
            if text:
                if _FIGURE_RE.search(text):
                    figures_omitted = True
                text = _FIGURE_RE.sub("", text).strip()
                if text:
                    chunks.append(text)
            if finished:
                break
            if next_frame is None or next_frame <= frame:
                break
            frame = next_frame
            if poll_interval > 0:
                await asyncio.sleep(poll_interval)
        else:
            truncated = True

        summary = "\n\n".join(chunks)
        return summary, truncated, len(summary), figures_omitted
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_academic.py -v
```

Expected: 4 passed. If `test_parse_sup` expects 18 but the fixture has a different count, inspect the fixture and adjust the assertion to `>= 10` (the fixture is fixed; `len(papers)` should equal the number of `sup_list` entries in `academic_sup.json`).

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/academic.py tests/test_academic.py
git commit -m "feat: parse academic papers, sub-questions, and summaries"
```

---

## Task 9: Service — WeChat search

**Files:**
- Create: `src/yuanbao_search_mcp/service.py`
- Test: `tests/test_service_weixin.py`

- [ ] **Step 1: Write the failing test**

`tests/test_service_weixin.py`:

```python
from datetime import date

import httpx
import respx

from yuanbao_search_mcp.service import YuanbaoService, filter_by_days


@respx.mock
async def test_search_weixin_defaults(settings, weixin_search_html) -> None:
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=weixin_search_html)
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_weixin("自进化")
        assert result.count == 20
        assert result.total_available == 26
        assert result.results[0].account == "词元潮汐"
        assert result.results[0].publish_time
        assert result.warnings == []
    finally:
        await service.aclose()


@respx.mock
async def test_search_weixin_account_filter(settings, weixin_search_html) -> None:
    respx.get("https://so.qq.com/isearch").mock(
        return_value=httpx.Response(200, text=weixin_search_html)
    )
    service = YuanbaoService(settings)
    try:
        result = await service.search_weixin("", account="词元潮汐")
        assert result.count >= 1
        assert all("词元潮汐" in (item.account or "") for item in result.results)
    finally:
        await service.aclose()


def test_filter_by_days_marks_unknown() -> None:
    from yuanbao_search_mcp.models import WeixinArticle

    items = [
        WeixinArticle(title="new", publish_time="2026-11-12", url="https://x/1"),
        WeixinArticle(title="old", publish_time="2026-01-01", url="https://x/2"),
        WeixinArticle(title="unknown", publish_time=None, url="https://x/3"),
    ]
    kept, undated = filter_by_days(items, days=7, today=date(2026, 11, 12))
    assert [item.title for item in kept] == ["new", "unknown"]
    assert kept[1].date_unknown is True
    assert undated == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/test_service_weixin.py -v
```

Expected: `ModuleNotFoundError` for `service`.

- [ ] **Step 3: Write `src/yuanbao_search_mcp/service.py`**

```python
"""High-level operations exposed by the MCP tools."""

from __future__ import annotations

import asyncio
from datetime import date
from urllib.parse import urlparse

from .academic import AcademicSession
from .client import (
    ArticleUnavailableError,
    HttpClient,
    TTLCache,
    UpstreamBlockedError,
    UpstreamError,
)
from .config import WECHAT_USER_AGENT, Settings
from .models import (
    AcademicPaper,
    AcademicSearchResult,
    ArticleResult,
    WeixinArticle,
    WeixinSearchResult,
    WebResult,
    WebSearchResult,
)
from .parsers import (
    extract_initial_cards,
    is_article_error_page,
    is_blocked_page,
    normalize_url,
    parse_date,
    parse_weixin_article,
    parse_weixin_cards,
    parse_web_cards,
)


def filter_by_days(
    items: list[WeixinArticle] | list[WebResult],
    days: int,
    today: date | None = None,
) -> tuple[list[WeixinArticle] | list[WebResult], int]:
    cutoff = (today or date.today()).toordinal() - days
    kept = []
    undated = 0
    for item in items:
        parsed = parse_date(item.publish_time) if isinstance(item, WeixinArticle) else parse_date(item.date)
        if parsed is None:
            item.date_unknown = True
            undated += 1
            kept.append(item)
        elif parsed.toordinal() >= cutoff:
            kept.append(item)
    return kept, undated


def sort_by_date(
    items: list[WeixinArticle] | list[WebResult],
) -> list[WeixinArticle] | list[WebResult]:
    def key(item: WeixinArticle | WebResult) -> tuple[int, int]:
        parsed = parse_date(item.publish_time) if isinstance(item, WeixinArticle) else parse_date(item.date)
        return (0 if parsed else 1, -(parsed.toordinal() if parsed else 0))

    return sorted(items, key=key)


class YuanbaoService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpClient(settings)
        self._weixin_cache: TTLCache[WeixinSearchResult] = TTLCache(settings.cache_ttl)
        self._web_cache: TTLCache[WebSearchResult] = TTLCache(settings.cache_ttl)
        self._article_cache: TTLCache[ArticleResult] = TTLCache(settings.article_cache_ttl)
        self._academic_cache: TTLCache[AcademicSearchResult] = TTLCache(
            settings.academic_cache_ttl
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def search_weixin(
        self,
        query: str,
        account: str | None = None,
        limit: int = 20,
        sort: str = "relevance",
        days: int | None = None,
    ) -> WeixinSearchResult:
        query = (query or "").strip()
        account = (account or "").strip() or None
        if not query and not account:
            raise ValueError("query or account is required")

        limit = max(1, min(limit, self.settings.weixin_max_results))
        if days is not None and days < 1:
            raise ValueError("days must be >= 1")
        cache_key = f"wx:{query}|{account}|{limit}|{sort}|{days}"
        cached = self._weixin_cache.get(cache_key)
        if cached is not None:
            return cached

        upstream_query = " ".join(part for part in (account, query) if part)
        html = await self.http.get(
            "https://so.qq.com/isearch",
            params={"query": upstream_query, "tab": "weixin_article"},
        )
        if is_blocked_page(html):
            raise UpstreamBlockedError("Yuanbao returned an anti-crawl page")

        articles = parse_weixin_cards(extract_initial_cards(html))
        if account:
            needle = account.casefold()
            articles = [
                item
                for item in articles
                if item.account and needle in item.account.casefold()
            ]

        total_available = len(articles)
        warnings: list[str] = []
        if days is not None:
            articles, undated = filter_by_days(articles, days)
            if undated:
                warnings.append(
                    f"{undated} result(s) had no publish date and were kept with date_unknown=true."
                )
        if sort == "date":
            articles = sort_by_date(articles)  # type: ignore[assignment]

        results = articles[:limit]
        if not results:
            warnings.append("No matching WeChat articles were found.")

        result = WeixinSearchResult(
            query=query,
            account=account,
            count=len(results),
            total_available=total_available,
            results=results,
            warnings=warnings,
        )
        self._weixin_cache.set(cache_key, result)
        return result

    async def read_article(self, url: str, max_chars: int = 20000) -> ArticleResult:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ("http", "https") or parsed_url.hostname != "mp.weixin.qq.com":
            raise ValueError("Only mp.weixin.qq.com article URLs are supported")

        max_chars = max(1000, min(max_chars, 100000))
        cache_key = f"article:{url}|{max_chars}"
        cached = self._article_cache.get(cache_key)
        if cached is not None:
            return cached

        html = await self.http.get(
            url,
            headers={"user-agent": WECHAT_USER_AGENT, "referer": "https://so.qq.com/"},
            max_bytes=15_000_000,
        )
        if is_blocked_page(html):
            raise ArticleUnavailableError("WeChat returned a verification page")
        if is_article_error_page(html) and "#js_content" not in html:
            raise ArticleUnavailableError("Article is deleted, restricted, or requires WeChat")

        parsed = parse_weixin_article(html)
        original_chars = len(parsed.content)
        content = parsed.content
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars].rsplit("\n\n", 1)[0] or content[:max_chars]
            truncated = True

        result = ArticleResult(
            title=parsed.title,
            account=parsed.account,
            publish_time=parsed.publish_time,
            url=normalize_url(url),
            content=content,
            char_count=len(content),
            original_chars=original_chars,
            truncated=truncated,
            images=parsed.images[:50],
            image_count=len(parsed.images),
        )
        self._article_cache.set(cache_key, result)
        return result

    async def search_web(
        self,
        query: str,
        limit: int = 10,
        scope: str = "all",
        sort: str = "relevance",
        days: int | None = None,
    ) -> WebSearchResult:
        query = (query or "").strip()
        if not query:
            raise ValueError("query is required")
        if scope not in ("all", "gov", "media"):
            raise ValueError("scope must be all, gov, or media")

        limit = max(1, min(limit, self.settings.web_max_results))
        if days is not None and days < 1:
            raise ValueError("days must be >= 1")
        cache_key = f"web:{query}|{limit}|{scope}|{sort}|{days}"
        cached = self._web_cache.get(cache_key)
        if cached is not None:
            return cached

        html = await self.http.get(
            "https://so.qq.com/isearch",
            params={"query": query, "tab": scope},
        )
        if is_blocked_page(html):
            raise UpstreamBlockedError("Yuanbao returned an anti-crawl page")

        results, related = parse_web_cards(extract_initial_cards(html))
        warnings: list[str] = []
        if days is not None:
            results, undated = filter_by_days(results, days)
            if undated:
                warnings.append(
                    f"{undated} result(s) had no publish date and were kept with date_unknown=true."
                )
        if sort == "date":
            results = sort_by_date(results)  # type: ignore[assignment]

        results = results[:limit]
        if not results:
            warnings.append("No matching web results were found.")

        result = WebSearchResult(
            query=query,
            scope=scope,  # type: ignore[arg-type]
            count=len(results),
            results=results,
            related_queries=related,
            warnings=warnings,
        )
        self._web_cache.set(cache_key, result)
        return result

    async def search_academic(
        self,
        query: str,
        limit: int = 10,
        include_summary: bool = False,
        summary_timeout: float = 45.0,
        include_subquestions: bool = True,
    ) -> AcademicSearchResult:
        query = (query or "").strip()
        if not query:
            raise ValueError("query is required")

        limit = max(1, min(limit, self.settings.academic_max_papers))
        summary_timeout = max(0.1, min(summary_timeout, 120.0))
        cache_key = (
            f"academic:{query}|{limit}|{include_summary}|"
            f"{summary_timeout}|{include_subquestions}"
        )
        cached = self._academic_cache.get(cache_key)
        if cached is not None:
            return cached

        session = AcademicSession(self.http, query)
        await session.create()

        sup_task = asyncio.create_task(session.fetch_sup())
        subq_task = (
            asyncio.create_task(session.fetch_sub_questions())
            if include_subquestions
            else None
        )

        # Wait for get_sup to start the academic generation before polling summary frames.
        sup_result = (await asyncio.gather(sup_task, return_exceptions=True))[0]

        summary_task = (
            asyncio.create_task(session.fetch_summary(summary_timeout))
            if include_summary
            else None
        )

        pending = [task for task in (subq_task, summary_task) if task is not None]
        pending_results = await asyncio.gather(*pending, return_exceptions=True)

        core_papers: list[AcademicPaper] = []
        sub_questions = []
        summary = None
        summary_truncated = False
        summary_chars = 0
        warnings: list[str] = []

        if isinstance(sup_result, Exception):
            warnings.append(f"Core papers could not be loaded: {sup_result}")
        else:
            core_papers = sup_result[:limit]

        index = 0
        if subq_task is not None:
            if isinstance(pending_results[index], Exception):
                warnings.append(f"Sub-questions could not be loaded: {pending_results[index]}")
            else:
                sub_questions = pending_results[index]
            index += 1

        figures_omitted = False
        if summary_task is not None:
            if isinstance(pending_results[index], Exception):
                warnings.append(f"AI summary failed: {pending_results[index]}")
            else:
                summary, summary_truncated, summary_chars, figures_omitted = pending_results[index]
                if figures_omitted:
                    warnings.append("Summary figure placeholders were omitted.")

        if not core_papers and not sub_questions:
            raise UpstreamError("Academic search failed for both papers and sub-questions")

        result = AcademicSearchResult(
            query=query,
            core_papers=core_papers,
            sub_questions=sub_questions,
            summary=summary,
            summary_truncated=summary_truncated,
            summary_char_count=summary_chars,
            warnings=warnings,
        )
        self._academic_cache.set(cache_key, result)
        return result
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_service_weixin.py -v
```

Expected: 3 passed. If the fixture's first account is not `词元潮汐`, inspect the fixture and update the assertion to the actual first account.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/service.py tests/test_service_weixin.py
git commit -m "feat: implement weixin search service"
```

---

## Task 10: Service — article reader

**Files:**
- Modify: `src/yuanbao_search_mcp/service.py`
- Test: `tests/test_service_article.py`

- [ ] **Step 1: Write the failing test**

`tests/test_service_article.py`:

```python
import httpx
import pytest
import respx

from yuanbao_search_mcp.service import YuanbaoService

ARTICLE_URL = "https://mp.weixin.qq.com/s?__biz=abc&mid=1&idx=1&sn=xyz"

_LONG = "Long paragraph. " * 200
ARTICLE_HTML = f"""
<!DOCTYPE html><html><body>
<h1 id="activity-name">Title</h1>
<span id="js_name">Account</span>
<em id="publish_time">2026-11-12</em>
<div id="js_content">
  <p>Paragraph one.</p>
  <p>Paragraph two.</p>
  <p>{_LONG}</p>
  <img data-src="https://mmbiz.qpic.cn/a.jpg" />
</div>
</body></html>
"""


@respx.mock
async def test_read_article(settings) -> None:
    respx.get(ARTICLE_URL).mock(return_value=httpx.Response(200, text=ARTICLE_HTML))
    service = YuanbaoService(settings)
    try:
        result = await service.read_article(ARTICLE_URL)
        assert result.title == "Title"
        assert result.account == "Account"
        assert result.char_count > 0
        assert result.images == ["https://mmbiz.qpic.cn/a.jpg"]
        assert result.truncated is False
    finally:
        await service.aclose()


@respx.mock
async def test_read_article_truncates(settings) -> None:
    respx.get(ARTICLE_URL).mock(return_value=httpx.Response(200, text=ARTICLE_HTML))
    service = YuanbaoService(settings)
    try:
        result = await service.read_article(ARTICLE_URL, max_chars=1000)
        assert result.original_chars > result.char_count
        assert result.truncated is True
    finally:
        await service.aclose()


async def test_read_article_rejects_non_weixin(settings) -> None:
    service = YuanbaoService(settings)
    try:
        with pytest.raises(ValueError):
            await service.read_article("https://example.com/article")
    finally:
        await service.aclose()
```

- [ ] **Step 2: Run the test to verify it fails or passes**

```bash
uv run pytest tests/test_service_article.py -v
```

Expected: the methods exist from Task 9, so the tests may pass already. If they pass, continue; this task is a verification and commit checkpoint. If they fail, fix the implementation.

- [ ] **Step 3: Add a blocked-article test**

Append to `tests/test_service_article.py`:

```python
@respx.mock
async def test_read_article_blocked(settings) -> None:
    respx.get(ARTICLE_URL).mock(
        return_value=httpx.Response(200, text="<html><body>环境异常</body></html>")
    )
    service = YuanbaoService(settings)
    try:
        with pytest.raises(Exception):
            await service.read_article(ARTICLE_URL)
    finally:
        await service.aclose()
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_service_article.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/service.py tests/test_service_article.py
git commit -m "test: cover article reader and truncation"
```

---

## Task 11: Service — web search

**Files:**
- Modify: `src/yuanbao_search_mcp/service.py`
- Test: `tests/test_service_web.py`

- [ ] **Step 1: Write the failing test**

`tests/test_service_web.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails or passes**

```bash
uv run pytest tests/test_service_web.py -v
```

Expected: the service method exists; if the RSC helper format is correct, tests pass. If `extract_initial_cards` returns `[]`, print the generated HTML and adjust the escaping.

- [ ] **Step 3: Fix any issues in `search_web`**

Confirm the `scope` value is passed as `tab` and the `related_queries` list is returned. No code changes are expected beyond Task 9.

- [ ] **Step 4: Run the full service tests**

```bash
uv run pytest tests/test_service_weixin.py tests/test_service_article.py tests/test_service_web.py -v
```

Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/service.py tests/test_service_web.py
git commit -m "test: cover web search service"
```

---

## Task 12: Service — academic search

**Files:**
- Modify: `src/yuanbao_search_mcp/service.py`
- Test: `tests/test_service_academic.py`

- [ ] **Step 1: Write the failing test**

`tests/test_service_academic.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails or passes**

```bash
uv run pytest tests/test_service_academic.py -v
```

Expected: the method exists; if the fixture's `sup_list` has fewer than 5 items, `len(result.core_papers) == 5` may fail. Inspect `academic_sup.json` and use `min(5, len(sup["data"]["sup_list"]))` in the assertion.

- [ ] **Step 3: Fix any issues in `search_academic`**

- Ensure `fetch_sup` and `fetch_sub_questions` run concurrently.
- Ensure `summary_timeout` is passed through.
- Ensure `warnings` are populated on partial failures.
- If `frame_get` returns 500 for `get_sup` and also for frames, the `fetch_summary` task may return empty; the test without summary should not start it.

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/yuanbao_search_mcp/service.py tests/test_service_academic.py
git commit -m "feat: implement academic search with partial results"
```

---

## Task 13: MCP server and tool registration

**Files:**
- Create: `src/yuanbao_search_mcp/server.py`
- Test: `tests/test_mcp_protocol.py`

- [ ] **Step 1: Write the failing protocol test**

`tests/test_mcp_protocol.py`:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def server_params(**env_overrides: str) -> StdioServerParameters:
    env = {**os.environ, **env_overrides}
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "yuanbao_search_mcp"],
        cwd=str(PROJECT_ROOT),
        env=env,
    )


async def test_lists_four_tools() -> None:
    async with Client(server_params()) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {
            "yuanbao_search_weixin_articles",
            "yuanbao_read_weixin_article",
            "yuanbao_search_academic",
            "yuanbao_search_web",
        }
        for tool in tools.tools:
            assert tool.input_schema
            assert tool.output_schema
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.open_world_hint is True


async def test_invalid_article_url_returns_tool_error() -> None:
    async with Client(server_params()) as client:
        result = await client.call_tool(
            "yuanbao_read_weixin_article",
            {"url": "https://example.com/not-weixin"},
        )
        assert result.is_error is True
        text = " ".join(
            block.text for block in result.content if getattr(block, "type", "") == "text"
        )
        assert "mp.weixin.qq.com" in text


async def test_disabled_tool_is_not_registered() -> None:
    async with Client(server_params(YUANBAO_ENABLE_WEB_SEARCH="false")) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert "yuanbao_search_web" not in names
        assert "yuanbao_search_weixin_articles" in names
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/test_mcp_protocol.py -v
```

Expected: `ModuleNotFoundError` for `server` or the server exits immediately.

- [ ] **Step 3: Write `src/yuanbao_search_mcp/server.py`**

```python
"""MCP server entry point and tool registration."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .client import (
    ArticleUnavailableError,
    UpstreamBlockedError,
    UpstreamError,
    UpstreamParseError,
    UpstreamTimeoutError,
)
from .config import Settings, load_settings
from .models import (
    AcademicSearchResult,
    ArticleResult,
    WeixinSearchResult,
    WebSearchResult,
)
from .service import YuanbaoService

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)


def _tool_error(exc: Exception) -> ToolError:
    if isinstance(exc, ValueError):
        return ToolError(str(exc))
    if isinstance(exc, UpstreamBlockedError):
        return ToolError(
            "Yuanbao blocked this request (rate limit or captcha). "
            "Try again later or reduce request frequency."
        )
    if isinstance(exc, ArticleUnavailableError):
        return ToolError(
            "Article is unavailable (deleted, restricted, or requires the WeChat client)."
        )
    if isinstance(exc, UpstreamTimeoutError):
        return ToolError("Upstream request timed out. Try again.")
    if isinstance(exc, UpstreamParseError):
        return ToolError(
            "Could not parse the upstream response. The site layout may have changed."
        )
    if isinstance(exc, UpstreamError):
        return ToolError(f"Upstream request failed: {exc}")
    return ToolError(f"Unexpected error: {exc}")


def build_server(settings: Settings) -> MCPServer:
    @asynccontextmanager
    async def lifespan(server: MCPServer):
        service = YuanbaoService(settings)
        try:
            yield service
        finally:
            await service.aclose()

    mcp = MCPServer(
        settings.server_name,
        title="Yuanbao Search MCP",
        description=(
            "Search WeChat official-account articles, read WeChat articles, "
            "search academic papers, and search the general web via Tencent Yuanbao."
        ),
        instructions=(
            "Use these tools for Chinese-language research. WeChat search is limited "
            "to roughly 28 results per query and has no pagination. Academic results "
            "include core papers and sub-questions; the AI summary is optional and may "
            "be partial. Web search does not support site: or Boolean operators. "
            "Always cite the returned URLs when summarizing."
        ),
        version=settings.version,
        lifespan=lifespan,
        log_level=settings.log_level,
    )

    def service(ctx: Context) -> YuanbaoService:
        return ctx.request_context.lifespan_context

    if settings.enable_weixin_search:

        @mcp.tool(
            name="yuanbao_search_weixin_articles",
            title="Search WeChat official-account articles",
            annotations=READ_ONLY,
            structured_output=True,
        )
        async def search_weixin_articles(
            ctx: Context,
            query: str = "",
            account: str | None = None,
            limit: int = settings.weixin_default_limit,
            sort: Literal["relevance", "date"] = "relevance",
            days: int | None = None,
        ) -> WeixinSearchResult:
            """Search WeChat official-account articles indexed by Yuanbao.

            Args:
                query: Keywords to search. Can be empty when account is provided.
                account: Optional official-account name; results are filtered by a
                    case-insensitive contains match on the account name.
                limit: Maximum results, 1-28. Default 20.
                sort: "relevance" (default) or "date" (newest first; undated last).
                days: Optional local filter for articles published in the last N days.

            Returns:
                Structured results with title, account, publish time, summary, URL,
                document ID, cover URL, and warnings.
            """
            try:
                return await service(ctx).search_weixin(
                    query=query,
                    account=account,
                    limit=limit,
                    sort=sort,
                    days=days,
                )
            except Exception as exc:
                raise _tool_error(exc) from exc

    if settings.enable_article_reader:

        @mcp.tool(
            name="yuanbao_read_weixin_article",
            title="Read a WeChat article",
            annotations=READ_ONLY,
            structured_output=True,
        )
        async def read_weixin_article(
            ctx: Context,
            url: str,
            max_chars: int = settings.article_max_chars,
        ) -> ArticleResult:
            """Read a WeChat official-account article and return its full text.

            Args:
                url: An http(s) URL on mp.weixin.qq.com.
                max_chars: Maximum characters to return, 1,000-100,000. Default 20,000.

            Returns:
                Title, account, publish time, lightweight Markdown body, character
                counts, truncation flag, and up to 50 content image URLs.
            """
            try:
                return await service(ctx).read_article(url=url, max_chars=max_chars)
            except Exception as exc:
                raise _tool_error(exc) from exc

    if settings.enable_academic_search:

        @mcp.tool(
            name="yuanbao_search_academic",
            title="Search academic papers",
            annotations=READ_ONLY,
            structured_output=True,
        )
        async def search_academic(
            ctx: Context,
            query: str,
            limit: int = settings.academic_default_limit,
            include_summary: bool = settings.academic_summary_default,
            summary_timeout: float = settings.academic_summary_timeout,
            include_subquestions: bool = True,
        ) -> AcademicSearchResult:
            """Search academic papers and optional AI-generated literature summaries.

            Args:
                query: Research question or keywords.
                limit: Number of core papers, 1-20. Default 10.
                include_summary: Generate the AI academic summary. Default false.
                summary_timeout: Summary timeout in seconds, 5-120. Default 45.
                include_subquestions: Include 8 sub-questions with up to 4 papers each.

            Returns:
                Core papers with citation IDs, authors, venue, year, citation count,
                abstract, evidence quotes; sub-questions; optional summary; warnings.
            """
            try:
                return await service(ctx).search_academic(
                    query=query,
                    limit=limit,
                    include_summary=include_summary,
                    summary_timeout=summary_timeout,
                    include_subquestions=include_subquestions,
                )
            except Exception as exc:
                raise _tool_error(exc) from exc

    if settings.enable_web_search:

        @mcp.tool(
            name="yuanbao_search_web",
            title="Search the general web",
            annotations=READ_ONLY,
            structured_output=True,
        )
        async def search_web(
            ctx: Context,
            query: str,
            limit: int = settings.web_default_limit,
            scope: Literal["all", "gov", "media"] = "all",
            sort: Literal["relevance", "date"] = "relevance",
            days: int | None = None,
        ) -> WebSearchResult:
            """Search the general web through Yuanbao.

            Args:
                query: Keywords to search.
                limit: Maximum results, 1-20. Default 10.
                scope: "all", "gov", or "media".
                sort: "relevance" (default) or "date" (newest first; undated last).
                days: Optional local filter for results published in the last N days.

            Returns:
                Results with title, URL, source, date, snippet, date_unknown flags,
                related search queries, and warnings. Does not support site: or
                Boolean operators.
            """
            try:
                return await service(ctx).search_web(
                    query=query,
                    limit=limit,
                    scope=scope,
                    sort=sort,
                    days=days,
                )
            except Exception as exc:
                raise _tool_error(exc) from exc

    return mcp


def main(argv: list[str] | None = None) -> None:
    settings = load_settings(argv)
    logging.basicConfig(
        level=settings.log_level,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = build_server(settings)
    if settings.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(
            transport="streamable-http",
            host=settings.host,
            port=settings.port,
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the protocol tests**

```bash
uv run pytest tests/test_mcp_protocol.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run `--help`**

```bash
uv run python -m yuanbao_search_mcp --help
```

Expected: usage text with `--transport`, `--host`, `--port`, `--log-level`, `--version`.

- [ ] **Step 6: Commit**

```bash
git add src/yuanbao_search_mcp/server.py src/yuanbao_search_mcp/__main__.py tests/test_mcp_protocol.py
git commit -m "feat: expose four mcp tools over stdio"
```

---

## Task 14: CLI and HTTP transport verification

**Files:**
- Modify: `src/yuanbao_search_mcp/server.py` (only if issues are found)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the CLI test**

`tests/test_cli.py`:

```python
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_help_lists_transport_options() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "yuanbao_search_mcp", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--transport" in result.stdout
    assert "--port" in result.stdout


def test_version_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "yuanbao_search_mcp", "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout
```

- [ ] **Step 2: Run the CLI tests**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Manually verify HTTP mode starts**

Run:

```bash
uv run python -m yuanbao_search_mcp --transport streamable-http --port 8765 &
SERVER_PID=$!
sleep 2
kill "$SERVER_PID"
wait "$SERVER_PID" 2>/dev/null || true
```

Expected: the process starts and stays running for two seconds with no traceback.
The MCP endpoint is `http://127.0.0.1:8765/mcp`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_cli.py src/yuanbao_search_mcp/server.py
git commit -m "test: verify cli and transports"
```

---

## Task 15: Documentation

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Create: `config.example.env`

- [ ] **Step 1: Write `config.example.env`**

```dotenv
# Transport
YUANBAO_TRANSPORT=stdio
YUANBAO_HOST=127.0.0.1
YUANBAO_PORT=8765
YUANBAO_LOG_LEVEL=INFO

# Tool switches
YUANBAO_ENABLE_WEIXIN_SEARCH=true
YUANBAO_ENABLE_ARTICLE_READER=true
YUANBAO_ENABLE_ACADEMIC_SEARCH=true
YUANBAO_ENABLE_WEB_SEARCH=true

# Defaults
YUANBAO_WEIXIN_DEFAULT_LIMIT=20
YUANBAO_WEB_DEFAULT_LIMIT=10
YUANBAO_ACADEMIC_DEFAULT_LIMIT=10
YUANBAO_ACADEMIC_SUMMARY_DEFAULT=false
YUANBAO_ACADEMIC_SUMMARY_TIMEOUT=45
YUANBAO_ARTICLE_MAX_CHARS=20000

# Network
YUANBAO_REQUEST_TIMEOUT=20
YUANBAO_MIN_INTERVAL=1.0
YUANBAO_CACHE_TTL=300
YUANBAO_ARTICLE_CACHE_TTL=1800
YUANBAO_ACADEMIC_CACHE_TTL=600
# YUANBAO_PROXY=http://127.0.0.1:7890
```

- [ ] **Step 2: Write the English README**

Use this structure and keep the exact snippets:

````markdown
# yuanbao-search-mcp

[English](README.md) | [简体中文](README.zh-CN.md)

MCP server for Tencent Yuanbao Search: WeChat official-account articles,
academic search, and general web search.

## Why this exists

Tencent Cloud's official Yuanbao Search API (`SearchPro`) explicitly excludes
WeChat official-account content for copyright reasons. This project uses the
public web surface of `so.qq.com` to cover that gap. It is not affiliated with
Tencent, and the upstream surface may change without notice.

## Tools

| Tool | What it does |
|---|---|
| `yuanbao_search_weixin_articles` | Search WeChat official-account articles |
| `yuanbao_read_weixin_article` | Read a WeChat article's title and full text |
| `yuanbao_search_academic` | Search core papers, sub-questions, optional AI summary |
| `yuanbao_search_web` | Search all / government / mainstream-media results |

## Install

```bash
git clone <your-repo-url> yuanbao-search-mcp
cd yuanbao-search-mcp
uv sync
```

## Run

stdio (default):

```bash
uv run yuanbao-search-mcp
```

Streamable HTTP:

```bash
uv run yuanbao-search-mcp --transport streamable-http --port 8765
# endpoint: http://127.0.0.1:8765/mcp
```

## Client configuration

### OpenCode

Add to `~/.config/opencode/opencode.jsonc`:

```json
{
  "mcp": {
    "yuanbao-search": {
      "type": "local",
      "command": [
        "uv",
        "run",
        "--directory",
        "/absolute/path/to/yuanbao-search-mcp",
        "yuanbao-search-mcp"
      ],
      "enabled": true
    }
  }
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "yuanbao-search": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/yuanbao-search-mcp",
        "yuanbao-search-mcp"
      ]
    }
  }
}
```

### Cursor / VS Code

Use the same stdio command, or point the client at
`http://127.0.0.1:8765/mcp` after starting HTTP mode.

### Claude Code

```bash
claude mcp add yuanbao-search -- uv run --directory /absolute/path/to/yuanbao-search-mcp yuanbao-search-mcp
```

## Configuration

Copy `config.example.env` to `.env`, or set `YUANBAO_*` variables in the
client's `env` block. See the table in `DESIGN.md` for the full list.

## Tool notes and limitations

- WeChat search returns roughly 28 results and has no pagination.
- WeChat account filtering uses a case-insensitive contains match and a local
  post-filter; it cannot guarantee every article from an account.
- `days` is a local filter; undated results are kept with `date_unknown=true`.
- WeChat article reading supports only `mp.weixin.qq.com` URLs.
- Academic AI summaries are off by default and may be partial.
- Web search does not support `site:` or Boolean operators.
- Use `sort=date` for newest-first ordering; undated results go last.

## Compliance

This is a personal research/reading tool. It is not affiliated with Tencent.
`so.qq.com/isearch` is disallowed by `so.qq.com/robots.txt`, and
`mp.weixin.qq.com` article pages are not open to general crawlers. Do not use
this project for high-frequency scraping, redistribution of article content, or
commercial use. Upstream data remains with its original authors and publishers.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest -q
uv run python scripts/smoke_test.py
```

## License

MIT for the code. Article and search content belongs to the original sources.
````

- [ ] **Step 3: Write the Chinese README**

Translate the same structure into `README.zh-CN.md`, keeping the code blocks
identical. Include the language link at the top.

- [ ] **Step 4: Verify the language links**

```bash
grep -n "README.zh-CN.md" README.md
grep -n "README.md" README.zh-CN.md
```

Expected: both commands print a match.

- [ ] **Step 5: Commit**

```bash
git add README.md README.zh-CN.md config.example.env
git commit -m "docs: add bilingual readme and config example"
```

---

## Task 16: Live smoke test

**Files:**
- Create: `scripts/smoke_test.py`

- [ ] **Step 1: Write the smoke test**

```python
"""Live smoke test for the four MCP tools.

Run with:
    uv run python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "yuanbao_search_mcp"],
        cwd=str(PROJECT_ROOT),
    )
    calls = [
        (
            "yuanbao_search_weixin_articles",
            {"query": "自进化", "limit": 3, "sort": "date"},
        ),
        (
            "yuanbao_search_academic",
            {"query": "大模型推理", "limit": 3, "include_summary": False},
        ),
        (
            "yuanbao_search_web",
            {"query": "人工智能", "limit": 3, "scope": "all"},
        ),
    ]
    failures = 0
    async with Client(params) as client:
        tools = await client.list_tools()
        print("tools:", [tool.name for tool in tools.tools])

        weixin = await client.call_tool(
            "yuanbao_search_weixin_articles",
            {"query": "自进化", "limit": 1},
        )
        if weixin.is_error:
            print("weixin search failed:", weixin.content)
            failures += 1
        else:
            results = (weixin.structured_content or {}).get("results") or []
            if not results:
                print("weixin search returned no results")
                failures += 1
            else:
                url = results[0]["url"]
                article = await client.call_tool(
                    "yuanbao_read_weixin_article",
                    {"url": url, "max_chars": 2000},
                )
                print("article chars:", (article.structured_content or {}).get("char_count"))
                if article.is_error:
                    print("article read failed:", article.content)
                    failures += 1

        for name, args in calls[1:]:
            result = await client.call_tool(name, args)
            print(name, "is_error=", result.is_error)
            print(json.dumps(result.structured_content, ensure_ascii=False)[:800])
            if result.is_error:
                failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 2: Run the smoke test**

```bash
uv run python scripts/smoke_test.py
```

Expected:
- `tools:` lists four tools.
- WeChat article `char_count` is greater than 0.
- Academic result has `core_papers` and `sub_questions`.
- Web result has `results`.
- Exit code 0.

If the live site is blocked, wait a minute and retry. Do not add this script to CI.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_test.py
git commit -m "test: add live smoke test"
```

---

## Task 17: CI and final verification

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `.gitignore` if needed

- [ ] **Step 1: Write the CI workflow**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install
        run: uv sync --frozen --dev
      - name: Lint
        run: uv run ruff check .
      - name: Test
        run: uv run pytest -q
```

- [ ] **Step 2: Run lint and tests locally**

```bash
uv run ruff check .
uv run pytest -q
```

Expected: `ruff` passes; all tests pass. No live-network tests run.

- [ ] **Step 3: Check the package entry points**

```bash
uv run python -m yuanbao_search_mcp --version
uv run yuanbao-search-mcp --version
```

Expected: both print `0.1.0` or the version line.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint and test workflow"
```

- [ ] **Step 5: Final repository check**

```bash
git status --short
git log --oneline -5
```

Expected: clean working tree; the last five commits show the scaffold, models,
config, client, parsers, service, server, docs, smoke test, and CI.

---

## Self-review checklist

Before considering the plan complete, verify:

- [ ] Every tool in `DESIGN.md` has a matching task and test.
- [ ] All four tools return Pydantic models and are registered with
      `structured_output=True`.
- [ ] `ToolError` is used for anticipated failures; partial academic results
      return warnings instead of errors.
- [ ] `account` filtering is case-insensitive contains matching.
- [ ] `days` filtering keeps undated results with `date_unknown=true`.
- [ ] `sort=date` places undated results last.
- [ ] Article URLs are restricted to `mp.weixin.qq.com`.
- [ ] No `site:` or Boolean-operator claims exist in tool descriptions.
- [ ] Rate limiting, caching, retries, and proxy config are wired.
- [ ] stdio is the default transport; Streamable HTTP is optional.
- [ ] README language links work; compliance notes are present.
- [ ] No live-network tests run in CI.
