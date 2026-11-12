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
