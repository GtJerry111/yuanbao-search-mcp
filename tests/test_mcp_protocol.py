from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def server_params(**env_overrides: str) -> StdioServerParameters:
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("YUANBAO_")
    }
    env.update(env_overrides)
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
