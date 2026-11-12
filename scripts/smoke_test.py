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
