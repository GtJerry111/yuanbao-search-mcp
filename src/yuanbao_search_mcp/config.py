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
